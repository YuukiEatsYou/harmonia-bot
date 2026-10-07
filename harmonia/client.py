"""The `Bot`: the object a bot author builds a project around.

It owns the REST client, the gateway, config, the cache, the command registry,
the event listeners and the loaded cogs. A launcher constructs it, loads a few
extensions and calls `run`; a cog reaches back through `self.bot`.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cog import Cog
from .commands.command import Command
from .config import Config
from .context import Context
from .errors import CommandError
from .gateway import Gateway
from .http import HTTPClient
from .models import (
    Category,
    Channel,
    CommandInvoke,
    Member,
    Message,
    MessageDelete,
    PresenceUpdate,
    ReactionUpdate,
    Role,
    TypingStart,
    User,
)
from .permissions import Permissions

log = logging.getLogger("harmonia")

# Gateway events whose payload maps cleanly onto a model. Anything else is
# delivered as the raw dict from the socket.
_EVENT_MODELS: dict[str, Callable[[dict], Any]] = {
    "message_create": Message.from_dict,
    "message_update": Message.from_dict,
    "message_delete": MessageDelete.from_dict,
    "message_reaction_add": ReactionUpdate.from_dict,
    "message_reaction_remove": ReactionUpdate.from_dict,
    "typing_start": TypingStart.from_dict,
    "presence_update": PresenceUpdate.from_dict,
    "channel_create": Channel.from_dict,
    "channel_update": Channel.from_dict,
    "category_create": Category.from_dict,
    "category_update": Category.from_dict,
    "role_create": Role.from_dict,
    "role_update": Role.from_dict,
}

_CACHE_REFRESH_EVENTS = {
    "channel_create",
    "channel_update",
    "channel_delete",
    "category_create",
    "category_update",
    "category_delete",
}


@dataclass
class Cache:
    """What the bot knows about the server between events."""

    channels: dict[str, Channel] = field(default_factory=dict)
    categories: dict[str, Category] = field(default_factory=dict)
    roles: dict[str, Role] = field(default_factory=dict)
    users: dict[str, User] = field(default_factory=dict)


class Bot:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        data_dir: str = "data",
        config_name: str | None = None,
        user_agent: str = "harmonia (python)",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.data_dir = Path(data_dir)
        self.http = HTTPClient(self.base_url, token, user_agent=user_agent)
        self.gateway = Gateway(self.base_url, token, self._on_dispatch, user_agent=user_agent)
        self.config = Config(config_name or "bot", self.data_dir)

        self.cache = Cache()
        self.user: User | None = None
        self.permissions = Permissions.NONE

        self.commands: dict[str, Command] = {}
        self.cogs: dict[str, Cog] = {}

        self._listeners: dict[str, list[Callable]] = {}
        self._ready = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()

    # --- events -----------------------------------------------------------

    def listen(self, name: str) -> Callable[[Callable], Callable]:
        """Register a listener for a gateway event (e.g. `"message_create"`).

        Use `"*"` to receive every event. The listener may be a coroutine
        function; each argument is the converted payload.
        """

        def decorate(func: Callable) -> Callable:
            self._listeners.setdefault(name.lower(), []).append(func)
            return func

        return decorate

    async def dispatch(self, name: str, *args: Any) -> None:
        """Call every listener registered for `name` (and for `"*"`)."""
        for key in (name.lower(), "*"):
            for listener in list(self._listeners.get(key, [])):
                try:
                    result = listener(*args)
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # noqa: BLE001 - one bad listener must not stop the rest
                    log.exception("listener for %s failed", name)

    async def wait_for(
        self,
        name: str,
        *,
        timeout: float | None = None,
        predicate: Callable[[Any], bool] | None = None,
    ) -> Any:
        """Wait for the next `name` event (optionally matching `predicate`)."""
        future: asyncio.Future = asyncio.get_running_loop().create_future()

        async def listener(*args: Any) -> None:
            value = args[0] if len(args) == 1 else args
            if predicate is not None and not predicate(value):
                return
            if not future.done():
                future.set_result(value)

        self._listeners.setdefault(name.lower(), []).append(listener)
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self._listeners[name.lower()].remove(listener)

    async def wait_until_ready(self, timeout: float | None = None) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout)

    # --- commands and cogs ------------------------------------------------

    def add_command(self, command: Command, *, cog: Cog | None = None) -> None:
        if cog is not None:
            command.cog = cog
        if command.name in self.commands:
            log.warning("replacing command /%s", command.name)
        self.commands[command.name] = command

    async def add_cog(self, cog: Cog) -> None:
        if not isinstance(cog, Cog):
            raise TypeError("add_cog expects a Cog instance")
        name = type(cog).__name__
        if name in self.cogs:
            raise ValueError(f"cog {name} is already loaded")
        self.cogs[name] = cog
        for command in cog._collect_commands().values():
            self.add_command(command, cog=cog)
        await cog.cog_load()
        log.info("loaded cog %s (%d command(s))", name, len(cog._collect_commands()))
        if self._ready.is_set():
            await self.register_commands()

    async def remove_cog(self, name: str) -> None:
        cog = self.cogs.pop(name, None)
        if cog is None:
            return
        for command_name in [n for n, c in self.commands.items() if c.cog is cog]:
            del self.commands[command_name]
        await cog.cog_unload()
        log.info("unloaded cog %s", name)
        if self._ready.is_set():
            await self.register_commands()

    async def load_extension(self, module_name: str) -> None:
        module = importlib.import_module(module_name)
        setup = getattr(module, "setup", None)
        if setup is None:
            cog_cls = next(
                (
                    obj
                    for obj in vars(module).values()
                    if inspect.isclass(obj) and issubclass(obj, Cog) and obj is not Cog
                ),
                None,
            )
            if cog_cls is None:
                raise TypeError(
                    f"{module_name} has no setup(bot) and no Cog subclass to load"
                )
            await self.add_cog(cog_cls(self))
            return
        result = setup(self)
        if inspect.isawaitable(result):
            await result

    async def unload_extension(self, module_name: str) -> None:
        module = importlib.import_module(module_name)
        for obj in vars(module).values():
            if inspect.isclass(obj) and issubclass(obj, Cog) and obj is not Cog:
                if obj.__name__ in self.cogs:
                    await self.remove_cog(obj.__name__)

    async def reload_extension(self, module_name: str) -> None:
        import importlib as _importlib

        await self.unload_extension(module_name)
        _importlib.reload(importlib.import_module(module_name))
        await self.load_extension(module_name)

    async def load_extensions(self, module_names: list[str]) -> None:
        """Load each extension in turn, reporting the ones that fail."""
        for module_name in module_names:
            try:
                await self.load_extension(module_name)
            except Exception:  # noqa: BLE001 - one bad cog must not stop the bot
                log.exception("could not load extension %s", module_name)

    async def register_commands(self) -> None:
        """Publish the current command set to the server (replaces the old one)."""
        registrations = [command.to_registration() for command in self.commands.values()]
        result = await self.http.register_commands(registrations)
        by_name = {
            entry["name"]: entry
            for entry in result
            if isinstance(entry, dict) and entry.get("name")
        }
        for name, command in self.commands.items():
            entry = by_name.get(name)
            command.id = entry.get("id") if entry else None
        names = ", ".join("/" + name for name in self.commands) or "none"
        log.info("registered %d command(s): %s", len(registrations), names)

    # --- lifecycle --------------------------------------------------------

    async def login(self) -> User:
        """Fetch the bot's identity, warm the cache and register commands."""
        self.user, self.permissions = await self.http.get_self()
        log.info("logged in as %s (%s)", self.user.name, self.user.account_type)
        await self.refresh_cache()
        await self.refresh_users()
        await self.register_commands()
        return self.user

    async def start(self) -> None:
        """Log in, connect the gateway and block until the connection ends."""
        await self.login()
        gateway_task = self._spawn(self.gateway.run())
        ready_task = asyncio.ensure_future(self._ready.wait())
        try:
            done, _ = await asyncio.wait(
                {gateway_task, ready_task}, return_when=asyncio.FIRST_COMPLETED
            )
            # If the gateway died before it was ever ready (a bad token, or the
            # bot was removed), there is nothing to wait for; just shut down.
            if ready_task in done and not gateway_task.done():
                log.info("gateway ready")
                await gateway_task
            else:
                log.error("the gateway ended before the bot became ready")
        finally:
            ready_task.cancel()
            await self.close()

    def run(self) -> None:
        """Blocking entry point for a launcher."""
        try:
            asyncio.run(self.start())
        except KeyboardInterrupt:
            pass

    async def close(self) -> None:
        await self.gateway.close()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for name in list(self.cogs):
            await self.remove_cog(name)
        await self.http.close()

    # --- cache ------------------------------------------------------------

    async def refresh_cache(self) -> None:
        snapshot = await self.http.get_channels()
        self.cache.channels = {channel.id: channel for channel in snapshot.channels}
        self.cache.categories = {category.id: category for category in snapshot.categories}
        self.cache.roles = {role.id: role for role in await self.http.get_roles()}

    async def refresh_roles(self) -> None:
        self.cache.roles = {role.id: role for role in await self.http.get_roles()}

    async def refresh_users(self) -> None:
        self.cache.users = {user.id: user for user in await self.http.get_directory()}

    # --- lookups ----------------------------------------------------------

    async def resolve_channel(self, value: str) -> Channel | None:
        key = value.lstrip("#").strip()
        if not self.cache.channels:
            await self._quiet(self.refresh_cache)
        if key in self.cache.channels:
            return self.cache.channels[key]
        lowered = key.lower()
        matches = [c for c in self.cache.channels.values() if c.name.lower() == lowered]
        return matches[0] if len(matches) == 1 else None

    async def resolve_role(self, value: str) -> Role | None:
        key = value.lstrip("@").strip()
        if not self.cache.roles:
            await self._quiet(self.refresh_roles)
        if key in self.cache.roles:
            return self.cache.roles[key]
        lowered = key.lower()
        matches = [r for r in self.cache.roles.values() if r.name.lower() == lowered]
        return matches[0] if len(matches) == 1 else None

    async def resolve_user(self, value: str) -> User | None:
        key = value.lstrip("@").strip()
        if not self.cache.users:
            await self._quiet(self.refresh_users)
        if key in self.cache.users:
            return self.cache.users[key]
        lowered = key.lower()
        for user in self.cache.users.values():
            if user.username.lower() == lowered or user.name.lower() == lowered:
                return user
        return None

    async def resolve_member(self, value: str) -> Member | None:
        """Resolve an argument to a member, degrading gracefully.

        `GET /members` carries roles and permissions but needs `ManageRoles`.
        The roster needs only `ViewChannels` and still carries roles, and the
        public directory needs `ViewChannels` too but has neither. Try them in
        that order, so a bot with modest permissions still resolves people (with
        empty `role_ids` at worst).
        """
        key = value.lstrip("@").strip()
        lowered = key.lower()

        def matches(member: Member) -> bool:
            return (
                member.id == key
                or member.user.username.lower() == lowered
                or member.user.name.lower() == lowered
            )

        for fetch in (self.http.get_members, self.http.get_roster):
            try:
                members = await fetch()
            except Exception:  # noqa: BLE001 - try the next source
                continue
            for member in members:
                if matches(member):
                    return member

        user = await self.resolve_user(key)
        return Member(user=user) if user else None

    @staticmethod
    async def _quiet(coro: Callable[[], Awaitable[None]]) -> None:
        try:
            await coro()
        except Exception:  # noqa: BLE001 - a stale cache is better than an error
            log.warning("cache refresh failed", exc_info=True)

    # --- gateway dispatch -------------------------------------------------

    async def _on_dispatch(self, name: str, data: Any) -> None:
        if name == "ready":
            payload = data or {}
            if payload.get("user"):
                self.user = User.from_dict(payload["user"])
            await self._quiet(self.refresh_cache)
            self._ready.set()
            await self.dispatch("ready", self.user)
            return

        if name == "command_invoke":
            self._spawn(self._handle_command_invoke(data))
            return

        if name in _CACHE_REFRESH_EVENTS:
            await self._quiet(self.refresh_cache)
        elif name in ("role_create", "role_update", "role_delete"):
            await self._quiet(self.refresh_roles)

        await self.dispatch(name, self._convert_event(name, data))

    def _convert_event(self, name: str, data: Any) -> Any:
        factory = _EVENT_MODELS.get(name)
        if factory is None or not isinstance(data, dict):
            return data
        try:
            return factory(data)
        except Exception:  # noqa: BLE001 - a payload we cannot model stays raw
            log.debug("could not model %s payload", name, exc_info=True)
            return data

    async def _handle_command_invoke(self, data: Any) -> None:
        invoke = CommandInvoke.from_dict(data if isinstance(data, dict) else {})
        command = self._find_command(invoke)
        if command is None:
            log.warning("invoke for unknown command /%s ignored", invoke.name)
            return

        ctx = Context(
            self,
            channel_id=invoke.channel_id,
            user_id=invoke.user_id,
            username=invoke.username,
            command=command,
            raw_args=invoke.args,
            interaction_id=invoke.interaction_id,
        )
        await self.dispatch("command", ctx)
        try:
            await command.run_checks(ctx)
            await command.invoke(ctx, invoke.args)
        except CommandError as error:
            await self._report(ctx, command, str(error))
        except Exception:  # noqa: BLE001
            log.exception("command /%s failed", command.name)
            await self._report(ctx, command, "something went wrong running that command")

    def _find_command(self, invoke: CommandInvoke) -> Command | None:
        if invoke.command_id:
            for command in self.commands.values():
                if command.id == invoke.command_id:
                    return command
        return self.commands.get(invoke.name)

    async def _report(self, ctx: Context, command: Command, message: str) -> None:
        try:
            await ctx.send(f"⚠️ {message}")
        except Exception:  # noqa: BLE001
            log.exception("could not report the failure of /%s", command.name)

    def _spawn(self, coro: Awaitable[Any]) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task
