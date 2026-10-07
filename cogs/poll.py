"""A cog that starts polls, showing arguments, flags and scoped config.

Examples:

    /poll "Pizza or tacos?" "Pizza" "Tacos"
    /poll "Where next?" "Beach" "Mountains" "City" --multiple --hours=48
    /poll-duration 48
"""

from __future__ import annotations

from harmonia import Cog, commands
from harmonia.errors import BadArgument
from harmonia.permissions import Permissions


class Poll(Cog):
    def __init__(self, bot) -> None:
        super().__init__(bot)
        self.config = bot.config.cog("poll")
        self.config.register(duration_hours=24, allow_multiple=False)

    @commands.command(
        name="poll",
        description='Start a poll: /poll "question" "option" "option" ...',
        required_permissions=Permissions.SEND_MESSAGES,
    )
    async def poll(
        self,
        ctx: commands.Context,
        question: str,
        *options: str,
        multiple: bool = False,
        hours: int = 0,
    ) -> None:
        if len(options) < 2:
            raise BadArgument(
                'give at least two options, each in quotes, '
                'like /poll "Pizza or tacos?" "Pizza" "Tacos"'
            )
        if len(options) > 10:
            raise BadArgument("a poll takes at most ten options")

        server = self.config.server()
        duration = hours or await server.get("duration_hours", 24)
        default_multiple = await server.get("allow_multiple", False)

        message = await self.bot.http.create_poll(
            ctx.channel_id,
            question,
            [{"text": option} for option in options],
            allow_multiple=multiple or default_multiple,
            duration_hours=duration or None,
        )
        await ctx.react("🗳️", message_id=message.id)

    @commands.command(
        name="poll-duration",
        description="Set how long new polls stay open, in hours (0 for no expiry)",
        required_permissions=Permissions.MANAGE_SERVER,
    )
    async def poll_duration(self, ctx: commands.Context, hours: int) -> None:
        await self.config.server().set("duration_hours", hours)
        if hours:
            await ctx.send(f"New polls will stay open for {hours} hour(s).")
        else:
            await ctx.send("New polls will never close on their own.")


async def setup(bot) -> None:
    await bot.add_cog(Poll(bot))
