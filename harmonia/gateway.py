"""The realtime half of the API.

`Gateway` holds the WebSocket connection: it greets with HELLO, IDENTIFYs with
the bot token, heartbeats on the interval the server asks for, and reconnects
with jittered backoff when the socket drops.

There is no `RESUME` in the Harmony protocol, so a reconnect is a fresh IDENTIFY
and a fresh `READY`: events that happened while the socket was down are simply
gone. That is why the framework re-dispatches `ready` on every connection and
why modules should treat it as "refetch what I care about" rather than "the
process just started".

Dispatching is handed to a callback the client owns; frames are delivered there
with the event name lowercased, e.g. `MESSAGE_CREATE` -> `message_create`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .errors import GatewayClosed

log = logging.getLogger("harmonia.gateway")

OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_HELLO = 10
OP_HEARTBEAT_ACK = 11

# Close codes from docs/API.md. Authenticating again cannot fix the first two,
# so they end the connection for good instead of triggering a reconnect loop.
_FATAL_CLOSE_CODES = {4004, 4005}

DispatchCallback = Callable[[str, Any], Awaitable[None]]


def derive_ws_url(base_url: str) -> str:
    """Turn an instance's HTTP base URL into its gateway WebSocket URL."""
    base = base_url.rstrip("/")
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :] + "/gateway"
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :] + "/gateway"
    if base.startswith(("wss://", "ws://")):
        return base + "/gateway"
    raise ValueError(f"base_url must be http(s)://, got {base_url!r}")


class Gateway:
    """A self-healing gateway connection."""

    def __init__(
        self,
        base_url: str,
        token: str,
        dispatch: DispatchCallback,
        *,
        user_agent: str = "harmonia (python)",
        max_backoff: float = 60.0,
    ) -> None:
        self.ws_url = derive_ws_url(base_url)
        self._token = token
        self._dispatch = dispatch
        self._user_agent = user_agent
        self._max_backoff = max_backoff
        self._closing = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._tasks: set[asyncio.Task] = set()

    async def run(self) -> None:
        """Connect and stay connected until `close()` is called.

        A fatal close (bad token, or the bot was removed) ends the loop; a
        transient one reconnects with exponential backoff and jitter.
        """
        backoff = 1.0
        while not self._closing:
            try:
                await self._connect_once()
                backoff = 1.0
            except asyncio.CancelledError:
                raise
            except GatewayClosed as error:
                if error.code in _FATAL_CLOSE_CODES:
                    log.error("gateway refused the connection: %s", error)
                    await self._safe_dispatch(
                        "gateway_closed", {"code": error.code, "reason": error.reason}
                    )
                    return
                log.warning("gateway connection ended: %s", error)
            except aiohttp.ClientError as error:
                log.warning("gateway connection failed: %s", error)
            except Exception:  # noqa: BLE001 - never let the loop die silently
                log.exception("unexpected gateway error")

            if self._closing:
                break
            delay = min(backoff, self._max_backoff) + random.uniform(0, 1)
            log.info("reconnecting to the gateway in %.1fs", delay)
            await asyncio.sleep(delay)
            backoff = min(backoff * 2, self._max_backoff)

    async def close(self) -> None:
        self._closing = True
        ws = self._ws
        if ws is not None and not ws.closed:
            await ws.close()

    async def _connect_once(self) -> None:
        session = aiohttp.ClientSession(headers={"User-Agent": self._user_agent})
        try:
            async with session.ws_connect(self.ws_url, heartbeat=None) as ws:
                self._ws = ws
                hello = await self._recv_frame(ws)
                interval_ms = int(hello.get("d", {}).get("heartbeat_interval", 45000))
                await ws.send_json({"op": OP_IDENTIFY, "d": {"token": self._token}})

                ack = _AckState()
                heartbeat = asyncio.create_task(self._heartbeat_loop(ws, interval_ms / 1000, ack))
                try:
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self._handle(ws, json.loads(msg.data), ack)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                finally:
                    heartbeat.cancel()
                    self._ws = None

                code = ws.close_code or 1006
                reason = ws.close_reason or ""
                raise GatewayClosed(code, reason)
        finally:
            await session.close()

    async def _heartbeat_loop(
        self, ws: aiohttp.ClientWebSocketResponse, interval: float, ack: _AckState
    ) -> None:
        while True:
            await asyncio.sleep(interval)
            if ack.pending:
                # The last beat went unanswered: the link is dead without having
                # closed, so drop it and let `run` reconnect.
                log.warning("heartbeat was not acknowledged; dropping the connection")
                await ws.close(code=4009, message=b"heartbeat ack missing")
                return
            ack.pending = True
            await ws.send_json({"op": OP_HEARTBEAT, "d": None})

    def _handle(self, ws: aiohttp.ClientWebSocketResponse, frame: dict, ack: _AckState) -> None:
        op = frame.get("op")
        if op == OP_HEARTBEAT_ACK:
            ack.pending = False
        elif op == OP_DISPATCH:
            name = frame.get("t")
            if name:
                self._schedule_dispatch(name.lower(), frame.get("d"))

    def _schedule_dispatch(self, name: str, data: Any) -> None:
        task = asyncio.ensure_future(self._dispatch(name, data))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _safe_dispatch(self, name: str, data: Any) -> None:
        try:
            await self._dispatch(name, data)
        except Exception:  # noqa: BLE001
            log.exception("dispatch of %s failed", name)

    async def _recv_frame(self, ws: aiohttp.ClientWebSocketResponse) -> dict:
        msg = await ws.receive()
        if msg.type != aiohttp.WSMsgType.TEXT:
            raise GatewayClosed(ws.close_code or 1006, ws.close_reason or "expected HELLO")
        return json.loads(msg.data)


class _AckState:
    __slots__ = ("pending",)

    def __init__(self) -> None:
        self.pending = False
