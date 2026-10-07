"""Cogs bundle commands and listeners into a loadable unit.

A cog is a plain class subclassing `Cog`; its slash commands are methods
decorated with `@commands.command`, and they are found and registered when the
cog is added to the bot. Optional `cog_load` / `cog_unload` hooks let a cog
start and stop its own background work.
"""

from __future__ import annotations

import inspect

from .commands.command import Command


class Cog:
    """Base class for a module of commands and listeners."""

    def __init__(self, bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Called after the cog is registered. Start background tasks here."""

    async def cog_unload(self) -> None:
        """Called before the cog is removed. Cancel background tasks here."""

    def _collect_commands(self) -> dict[str, Command]:
        """The `Command` objects declared on this cog, bound to this instance."""
        found: dict[str, Command] = {}
        for name, _member in inspect.getmembers(type(self), lambda m: isinstance(m, Command)):
            found[name] = getattr(self, name)
        return found

    def __repr__(self) -> str:
        return f"<{type(self).__name__}>"
