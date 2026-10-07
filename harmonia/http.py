"""The REST half of the API.

`HTTPClient` owns one `aiohttp.ClientSession`, attaches the bot token, retries
the transient failures (429 and 5xx) and decodes the JSON. On top of that
transport it exposes one typed method per endpoint the framework and the bundled
cogs need; adding another is a thin wrapper over `request`.

The token is a credential: it is never logged, and it is only ever placed in the
`Authorization` header.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from .errors import http_exception_from_response
from .models import (
    Ban,
    Category,
    Channel,
    Emoji,
    Member,
    Message,
    Poll,
    Role,
    User,
)
from .permissions import Permissions

log = logging.getLogger("harmonia.http")


@dataclass(slots=True)
class ChannelsSnapshot:
    """The payload of `GET /channels`: the tree plus the caller's read state."""

    categories: list[Category] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    default_channel_id: str | None = None
    unread_channel_ids: list[str] = field(default_factory=list)
    mention_channel_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None) -> ChannelsSnapshot:
        data = data or {}
        return cls(
            categories=[Category.from_dict(item) for item in data.get("categories") or []],
            channels=[Channel.from_dict(item) for item in data.get("channels") or []],
            default_channel_id=data.get("defaultChannelId"),
            unread_channel_ids=list(data.get("unreadChannelIds") or []),
            mention_channel_ids=list(data.get("mentionChannelIds") or []),
        )


class HTTPClient:
    """A thin, retrying client over Harmony's REST API."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        api_prefix: str = "/api/v1",
        user_agent: str = "harmonia (python)",
        session: aiohttp.ClientSession | None = None,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.rest_url = self.base_url + api_prefix
        self.token = token
        self.max_retries = max_retries
        self._session = session
        self._owns_session = session is None
        self._default_headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": user_agent,
            "Accept": "application/json",
        }

    # --- transport --------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        retries: int | None = None,
    ) -> Any:
        """Perform one API call and return the decoded body.

        Retries `429` (honoring `Retry-After` when present) and `5xx` with
        exponential backoff and jitter. Any other non-2xx status raises the
        matching `HTTPException`. A `204` or empty body returns `None`.
        """
        session = await self._get_session()
        url = self.rest_url + path
        attempts = self.max_retries if retries is None else retries
        merged_headers = dict(self._default_headers)
        if headers:
            merged_headers.update(headers)

        # aiohttp otherwise stamps every bodyless POST/PUT/PATCH/DELETE with
        # `Content-Type: application/octet-stream`, which the server refuses with
        # 415 for routes that take no body. Suppress the auto header only when we
        # are sending nothing; a JSON or multipart body keeps its own.
        skip_auto_headers = {"Content-Type"} if json is None and data is None else None

        for attempt in range(attempts + 1):
            try:
                async with session.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    data=data,
                    headers=merged_headers,
                    skip_auto_headers=skip_auto_headers,
                ) as response:
                    if response.status == 204 or response.status == 205:
                        return None
                    body = await response.read()
                    if response.status >= 400:
                        if self._should_retry(response.status, attempt, attempts):
                            await self._backoff(attempt, response.headers.get("Retry-After"))
                            continue
                        raise http_exception_from_response(
                            response.status,
                            self._decode_maybe(body, response.headers.get("Content-Type", "")),
                            method=method,
                            path=path,
                        )
                    return self._decode_maybe(body, response.headers.get("Content-Type", ""))
            except aiohttp.ClientError as error:
                if attempt < attempts:
                    log.warning("request %s %s failed (%s); retrying", method, path, error)
                    await self._backoff(attempt, None)
                    continue
                raise

        raise AssertionError("unreachable")  # pragma: no cover

    @staticmethod
    def _decode_maybe(body: bytes, content_type: str) -> Any:
        if not body:
            return None
        if "json" in content_type:
            try:
                return _json.loads(body)
            except ValueError:
                return body.decode(errors="replace")
        return body.decode(errors="replace")

    @staticmethod
    def _should_retry(status: int, attempt: int, attempts: int) -> bool:
        return attempt < attempts and (status == 429 or status >= 500)

    @staticmethod
    async def _backoff(attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = 0.0
            if delay > 0:
                await asyncio.sleep(min(delay, 30.0))
                return
        await asyncio.sleep(min(2**attempt, 10.0) + random.uniform(0, 0.5))

    async def close(self) -> None:
        if self._session is not None and not self._session.closed and self._owns_session:
            await self._session.close()

    # --- health and meta --------------------------------------------------

    async def get_health(self) -> dict:
        return await self.request("GET", "/health")

    async def get_meta(self) -> dict:
        return await self.request("GET", "/meta")

    # --- identity ---------------------------------------------------------

    async def get_self(self) -> tuple[User, Permissions]:
        """`GET /auth/me` -> the bot's own user and its effective permissions."""
        payload = await self.request("GET", "/auth/me") or {}
        return User.from_dict(payload.get("user")), Permissions.from_value(
            payload.get("permissions", "0")
        )

    # --- channels ---------------------------------------------------------

    async def get_channels(self) -> ChannelsSnapshot:
        return ChannelsSnapshot.from_dict(await self.request("GET", "/channels"))

    async def get_channel(self, channel_id: str) -> Channel:
        snapshot = await self.get_channels()
        for channel in snapshot.channels:
            if channel.id == channel_id:
                return channel
        raise KeyError(channel_id)

    async def set_typing(self, channel_id: str) -> None:
        await self.request("POST", f"/channels/{channel_id}/typing")

    # --- messages ---------------------------------------------------------

    async def get_messages(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before: str | None = None,
        before_id: str | None = None,
    ) -> list[Message]:
        params: dict[str, Any] = {"limit": limit}
        if before:
            params["before"] = before
        if before_id:
            params["beforeId"] = before_id
        payload = await self.request("GET", f"/channels/{channel_id}/messages", params=params) or {}
        return [Message.from_dict(item) for item in payload.get("messages") or []]

    async def send_message(
        self,
        channel_id: str,
        content: str | None = None,
        *,
        attachment_ids: list[str] | None = None,
        reply_to: str | None = None,
    ) -> Message:
        body: dict[str, Any] = {}
        if content is not None:
            body["content"] = content
        if attachment_ids:
            body["attachmentIds"] = attachment_ids
        if reply_to:
            body["replyToId"] = reply_to
        payload = await self.request("POST", f"/channels/{channel_id}/messages", json=body)
        return Message.from_dict(payload)

    async def edit_message(self, message_id: str, content: str) -> Message:
        payload = await self.request(
            "PATCH", f"/messages/{message_id}", json={"content": content}
        )
        return Message.from_dict(payload)

    async def delete_message(self, message_id: str) -> None:
        await self.request("DELETE", f"/messages/{message_id}")

    # --- reactions --------------------------------------------------------

    async def add_reaction(
        self, message_id: str, emoji: str, *, emoji_id: str | None = None
    ) -> None:
        body: dict[str, Any] = {"emoji": emoji}
        if emoji_id:
            body["emojiId"] = emoji_id
        await self.request("POST", f"/messages/{message_id}/reactions", json=body)

    async def remove_reaction(
        self, message_id: str, emoji: str, *, emoji_id: str | None = None
    ) -> None:
        body: dict[str, Any] = {"emoji": emoji}
        if emoji_id:
            body["emojiId"] = emoji_id
        await self.request("DELETE", f"/messages/{message_id}/reactions", json=body)

    # --- polls ------------------------------------------------------------

    async def create_poll(
        self,
        channel_id: str,
        question: str,
        options: list[dict[str, Any]],
        *,
        allow_multiple: bool = False,
        duration_hours: int | None = 24,
        reply_to: str | None = None,
    ) -> Message:
        body: dict[str, Any] = {
            "question": question,
            "options": options,
            "allowMultiple": allow_multiple,
            "durationHours": duration_hours,
        }
        if reply_to:
            body["replyToId"] = reply_to
        payload = await self.request("POST", f"/channels/{channel_id}/polls", json=body)
        return Message.from_dict(payload)

    async def vote_poll(self, message_id: str, option_ids: list[str]) -> Poll:
        payload = await self.request(
            "PUT", f"/messages/{message_id}/poll/votes", json={"optionIds": option_ids}
        )
        return Poll.from_dict(payload)

    async def end_poll(self, message_id: str) -> Poll:
        payload = await self.request("POST", f"/messages/{message_id}/poll/end")
        return Poll.from_dict(payload)

    async def get_poll_voters(self, message_id: str, option_id: str) -> dict:
        return await self.request(
            "GET", f"/messages/{message_id}/poll/voters", params={"optionId": option_id}
        )

    # --- roles and members ------------------------------------------------

    async def get_roles(self) -> list[Role]:
        payload = await self.request("GET", "/roles") or {}
        return [Role.from_dict(item) for item in payload.get("roles") or []]

    async def get_members(self) -> list[Member]:
        payload = await self.request("GET", "/members") or {}
        return [Member.from_dict(item) for item in payload.get("members") or []]

    async def get_roster(self) -> list[Member]:
        payload = await self.request("GET", "/members/roster") or {}
        return [Member.from_dict(item) for item in payload.get("members") or []]

    async def get_directory(self) -> list[User]:
        payload = await self.request("GET", "/members/directory") or {}
        return [User.from_dict(item) for item in payload.get("users") or []]

    async def get_profile(self, user_id: str) -> dict:
        return await self.request("GET", f"/users/{user_id}/profile")

    # --- moderation -------------------------------------------------------

    async def kick_member(self, user_id: str) -> None:
        await self.request("POST", f"/members/{user_id}/kick")

    async def ban_member(self, user_id: str, reason: str | None = None) -> None:
        body = {"reason": reason} if reason else {}
        await self.request("PUT", f"/members/{user_id}/ban", json=body)

    async def unban_member(self, user_id: str) -> None:
        await self.request("DELETE", f"/members/{user_id}/ban")

    async def timeout_member(self, user_id: str, duration_minutes: int) -> None:
        await self.request(
            "PUT", f"/members/{user_id}/timeout", json={"durationMinutes": duration_minutes}
        )

    async def remove_timeout(self, user_id: str) -> None:
        await self.request("DELETE", f"/members/{user_id}/timeout")

    async def get_bans(self) -> list[Ban]:
        payload = await self.request("GET", "/bans") or {}
        return [Ban.from_dict(item) for item in payload.get("bans") or []]

    # --- emoji ------------------------------------------------------------

    async def get_emojis(self) -> list[Emoji]:
        payload = await self.request("GET", "/emojis") or {}
        return [Emoji.from_dict(item) for item in payload.get("emojis") or []]

    # --- slash commands ---------------------------------------------------

    async def register_commands(self, commands: list[dict[str, Any]]) -> list[dict]:
        """`PUT /bots/@me/commands` - replaces the bot's whole command set."""
        payload = await self.request(
            "PUT", "/bots/@me/commands", json={"commands": commands}
        )
        if isinstance(payload, dict):
            return list(payload.get("commands") or [])
        return list(payload or [])

    async def get_registered_commands(self) -> list[dict]:
        payload = await self.request("GET", "/bots/@me/commands")
        if isinstance(payload, dict):
            return list(payload.get("commands") or [])
        return list(payload or [])
