"""A cog using typed converters and permission requirements.

Examples:

    /kick bob --reason="spamming"
    /ban bob
    /timeout bob 30
    /untimeout bob
    /unban 1398164034464776202
    /whois bob

Each command declares the permission the server checks before the invocation
reaches the bot; the `Member`/`User` parameters are resolved from the argument
string by the framework's converters.
"""

from __future__ import annotations

from harmonia import Cog, commands
from harmonia.models import Member
from harmonia.permissions import Permissions


class Moderation(Cog):
    @commands.command(
        name="kick",
        description="Kick a member",
        required_permissions=Permissions.KICK_MEMBERS,
    )
    async def kick(self, ctx: commands.Context, member: Member, *, reason: str = "") -> None:
        await self.bot.http.kick_member(member.id)
        await ctx.send(_done("Kicked", member, reason))

    @commands.command(
        name="ban",
        description="Ban a member",
        required_permissions=Permissions.BAN_MEMBERS,
    )
    async def ban(self, ctx: commands.Context, member: Member, *, reason: str = "") -> None:
        await self.bot.http.ban_member(member.id, reason or None)
        await ctx.send(_done("Banned", member, reason))

    @commands.command(
        name="unban",
        description="Unban a user by their id",
        required_permissions=Permissions.BAN_MEMBERS,
    )
    async def unban(self, ctx: commands.Context, user_id: str) -> None:
        await self.bot.http.unban_member(user_id)
        await ctx.send(f"Unbanned {user_id}.")

    @commands.command(
        name="timeout",
        description="Time a member out, in minutes",
        required_permissions=Permissions.MODERATE_MEMBERS,
    )
    async def timeout(self, ctx: commands.Context, member: Member, minutes: int) -> None:
        await self.bot.http.timeout_member(member.id, minutes)
        await ctx.send(f"{member.user.username} is timed out for {minutes} minute(s).")

    @commands.command(
        name="untimeout",
        description="Clear a member's timeout",
        required_permissions=Permissions.MODERATE_MEMBERS,
    )
    async def untimeout(self, ctx: commands.Context, member: Member) -> None:
        await self.bot.http.remove_timeout(member.id)
        await ctx.send(f"Cleared {member.user.username}'s timeout.")

    @commands.command(
        name="whois",
        description="Show a member's profile",
        required_permissions=Permissions.VIEW_CHANNELS,
    )
    async def whois(self, ctx: commands.Context, member: Member) -> None:
        # The profile is readable with ViewChannels, so this works even when the
        # bot lacks ManageRoles and only resolved a bare user.
        profile = await self.bot.http.get_profile(member.id)
        lines = [f"**{member.name}** (@{member.user.username}, id `{member.id}`)"]
        if profile.get("bio"):
            lines.append(f"bio: {profile['bio']}")
        if profile.get("status"):
            lines.append(f"status: {profile['status']}")
        for site, url in (profile.get("socialLinks") or {}).items():
            if url:
                lines.append(f"{site}: {url}")
        roles = [
            self.bot.cache.roles[role_id].name
            for role_id in member.role_ids
            if role_id in self.bot.cache.roles
        ]
        if roles:
            lines.append(f"roles: {', '.join(roles)}")
        if member.online is not None:
            lines.append("online" if member.online else "offline")
        await ctx.send("\n".join(lines))


def _done(verb: str, member: Member, reason: str) -> str:
    text = f"{verb} {member.user.username}."
    return f"{text} Reason: {reason}" if reason else text


async def setup(bot) -> None:
    await bot.add_cog(Moderation(bot))
