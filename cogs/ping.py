"""A minimal cog: one slash command, plus a listener for the ready event.

This is the smallest useful shape of a cog. Load it with
`await bot.load_extension("cogs.ping")`.
"""

from __future__ import annotations

import logging

from harmonia import Cog, commands

log = logging.getLogger("cogs.ping")


class Ping(Cog):
    @commands.command(name="ping", description="Check that the bot is alive")
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.send("Pong! 🏓")

    @commands.command(name="info", description="Show what the bot can currently see")
    async def info(self, ctx: commands.Context) -> None:
        channels = len(self.bot.cache.channels)
        roles = len(self.bot.cache.roles)
        who = self.bot.user.username if self.bot.user else "?"
        await ctx.send(
            f"Connected to {self.bot.base_url} as {who}. "
            f"I can see {channels} channel(s) and {roles} role(s)."
        )

    async def cog_load(self) -> None:
        # `ready` fires after every (re)connection, so this is also the hook to
        # re-sync anything cached if the gateway dropped.
        self.bot.listen("ready")(self._on_ready)

    async def _on_ready(self, user) -> None:
        log.info("ready as %s; %d channel(s) cached", user, len(self.bot.cache.channels))


async def setup(bot) -> None:
    await bot.add_cog(Ping(bot))
