"""The permission bitfield, mirroring the flags in docs/API.md.

Over the wire a permission set is a decimal string (JSON cannot carry the full
bitfield safely), so `from_value` accepts anything the server sends and
`to_value` produces the string the API expects.
"""

from __future__ import annotations

from enum import IntFlag


class Permissions(IntFlag):
    NONE = 0
    VIEW_CHANNELS = 1 << 0
    SEND_MESSAGES = 1 << 1
    MANAGE_MESSAGES = 1 << 2
    ATTACH_FILES = 1 << 3
    EMBED_LINKS = 1 << 4
    ADD_REACTIONS = 1 << 5
    MANAGE_CHANNELS = 1 << 6
    MANAGE_ROLES = 1 << 7
    MANAGE_EMOJIS = 1 << 8
    MANAGE_SERVER = 1 << 9
    KICK_MEMBERS = 1 << 10
    BAN_MEMBERS = 1 << 11
    CREATE_INVITES = 1 << 12
    MENTION_EVERYONE = 1 << 13
    ADMINISTRATOR = 1 << 14
    MODERATE_MEMBERS = 1 << 15
    MANAGE_MEMBERS = 1 << 16
    MANAGE_EVENTS = 1 << 17

    @classmethod
    def from_value(cls, value: str | int | None) -> Permissions:
        """Parse a bitfield as the API sends it, or the integer form.

        Unknown bits are preserved rather than dropped, so a flag added by a
        newer server survives a round trip through the framework.
        """
        if value is None:
            return cls.NONE
        if isinstance(value, str):
            value = int(value or "0")
        return cls(value)

    def to_value(self) -> str:
        """The decimal-string form the API expects."""
        return str(int(self))

    def has(self, *flags: Permissions) -> bool:
        """Whether every one of `flags` is present.

        `Administrator` implies every other flag, so a holder of it passes any
        check, matching how the server resolves permissions.
        """
        if not flags:
            return True
        if self & Permissions.ADMINISTRATOR:
            return True
        return all(int(self) & int(flag) == int(flag) for flag in flags)

    def __str__(self) -> str:
        if self == Permissions.NONE:
            return "NONE"
        names = [flag.name for flag in Permissions if flag is not Permissions.NONE and flag & self]
        return "|".join(names) or "NONE"
