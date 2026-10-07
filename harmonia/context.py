"""The context handed to a running command.

A Harmony slash command is not an interaction object: the server forwards the
raw text a member typed and the bot replies through the ordinary API as itself.
So a `Context` is mostly a convenience wrapper around "this channel, this
invoker", plus shortcuts for the writes a command usually makes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import Message, User

if TYPE_CHECKING:
    from .client import Bot
    from .commands.command import Command
    from .models import Channel, Member


class Context:
    """Everything a command needs to know about the invocation, and to answer."""

    def __init__(
        self,
        bot: Bot,
        *,
        channel_id: str,
        user_id: str,
        username: str,
        command: Command | None = None,
        raw_args: str = "",
        interaction_id: str = "",
    ) -> None:
        self.bot = bot
        self.channel_id = channel_id
        self.user_id = user_id
        self.username = username
        self.command = command
        self.raw_args = raw_args
        self.interaction_id = interaction_id
        self._last_message: Message | None = None

    @property
    def channel(self) -> Channel | None:
        """The invoking channel, from the cache (None if it is not known yet)."""
        return self.bot.cache.channels.get(self.channel_id)

    @property
    def author_mention(self) -> str:
        return f"@{self.username}"

    async def send(
        self,
        content: str | None = None,
        *,
        reply_to: str | None = None,
        attachment_ids: list[str] | None = None,
    ) -> Message:
        """Post a message to the invoking channel as the bot."""
        message = await self.bot.http.send_message(
            self.channel_id, content, attachment_ids=attachment_ids, reply_to=reply_to
        )
        self._last_message = message
        return message

    async def react(
        self,
        emoji: str,
        *,
        emoji_id: str | None = None,
        message_id: str | None = None,
    ) -> None:
        """React to a message, defaulting to the one this command last sent."""
        target = message_id or (self._last_message.id if self._last_message else None)
        if target is None:
            raise RuntimeError("no message to react to; send one first or pass message_id")
        await self.bot.http.add_reaction(target, emoji, emoji_id=emoji_id)

    async def typing(self) -> None:
        await self.bot.http.set_typing(self.channel_id)

    async def fetch_channel(self) -> Channel:
        return await self.bot.http.get_channel(self.channel_id)

    async def fetch_author(self) -> User | None:
        return await self.bot.resolve_user(self.user_id)

    async def fetch_member(self) -> Member | None:
        return await self.bot.resolve_member(self.user_id)
