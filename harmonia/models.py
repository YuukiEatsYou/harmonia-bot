"""Typed views over the Harmony API object shapes.

Every model mirrors a `type` in docs/API.md and is built from a decoded JSON
value with `from_dict`, which tolerates absent fields by falling back to a
sensible default. Models describe the wire, so field names are snake_case here
and camelCase there.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .permissions import Permissions


def _list(items, factory):
    return [factory(item) for item in items or []]


@dataclass(slots=True)
class User:
    id: str = ""
    username: str = ""
    display_name: str | None = None
    avatar_hash: str | None = None
    role_color: int | None = None
    name_color: int | None = None
    account_type: str = "user"
    is_owner: bool = False
    badge: str | None = None
    created_at: str | None = None
    timed_out_until: str | None = None
    show_typing: bool = True
    notify_major: bool = True
    notify_minor: bool = False
    discord_id: str | None = None
    sync_discord_avatar: bool = False
    has_password: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> User:
        data = data or {}
        return cls(
            id=data.get("id", ""),
            username=data.get("username", ""),
            display_name=data.get("displayName"),
            avatar_hash=data.get("avatarHash"),
            role_color=data.get("roleColor"),
            name_color=data.get("nameColor"),
            account_type=data.get("accountType", "user"),
            is_owner=bool(data.get("isOwner", False)),
            badge=data.get("badge"),
            created_at=data.get("createdAt"),
            timed_out_until=data.get("timedOutUntil"),
            show_typing=bool(data.get("showTyping", True)),
            notify_major=bool(data.get("notifyMajor", True)),
            notify_minor=bool(data.get("notifyMinor", False)),
            discord_id=data.get("discordId"),
            sync_discord_avatar=bool(data.get("syncDiscordAvatar", False)),
            has_password=bool(data.get("hasPassword", False)),
        )

    @property
    def is_bot(self) -> bool:
        return self.account_type == "bot"

    @property
    def is_ghost(self) -> bool:
        return self.account_type == "ghost"

    @property
    def name(self) -> str:
        return self.display_name or self.username

    @property
    def mention(self) -> str:
        return f"@{self.username}"

    def __str__(self) -> str:
        return self.name


@dataclass(slots=True)
class Category:
    id: str = ""
    name: str = ""
    position: int = 0
    required_role_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> Category:
        data = data or {}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            position=data.get("position", 0),
            required_role_id=data.get("requiredRoleId"),
        )

    def __str__(self) -> str:
        return self.name


@dataclass(slots=True)
class Channel:
    id: str = ""
    name: str = ""
    topic: str | None = None
    type: str = "text"
    category_id: str | None = None
    position: int = 0
    created_at: str | None = None
    discord_channel_id: str | None = None
    required_role_id: str | None = None
    slowmode_seconds: int = 0

    @classmethod
    def from_dict(cls, data: dict | None) -> Channel:
        data = data or {}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            topic=data.get("topic"),
            type=data.get("type", "text"),
            category_id=data.get("categoryId"),
            position=data.get("position", 0),
            created_at=data.get("createdAt"),
            discord_channel_id=data.get("discordChannelId"),
            required_role_id=data.get("requiredRoleId"),
            slowmode_seconds=data.get("slowmodeSeconds", 0),
        )

    @property
    def mention(self) -> str:
        return f"#{self.name}"

    def __str__(self) -> str:
        return self.name


@dataclass(slots=True)
class Attachment:
    id: str = ""
    message_id: str | None = None
    filename: str = ""
    content_type: str = ""
    size: int = 0
    width: int | None = None
    height: int | None = None
    hash: str = ""
    created_at: str | None = None
    source_url: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> Attachment:
        data = data or {}
        return cls(
            id=data.get("id", ""),
            message_id=data.get("messageId"),
            filename=data.get("filename", ""),
            content_type=data.get("contentType", ""),
            size=data.get("size", 0),
            width=data.get("width"),
            height=data.get("height"),
            hash=data.get("hash", ""),
            created_at=data.get("createdAt"),
            source_url=data.get("sourceUrl"),
        )


@dataclass(slots=True)
class Reaction:
    emoji: str = ""
    emoji_id: str | None = None
    count: int = 0
    me: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> Reaction:
        data = data or {}
        return cls(
            emoji=data.get("emoji", ""),
            emoji_id=data.get("emojiId"),
            count=data.get("count", 0),
            me=bool(data.get("me", False)),
        )


@dataclass(slots=True)
class MessageReference:
    id: str = ""
    author: User | None = None
    content: str = ""
    deleted: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> MessageReference:
        data = data or {}
        author = data.get("author")
        return cls(
            id=data.get("id", ""),
            author=User.from_dict(author) if author else None,
            content=data.get("content", ""),
            deleted=bool(data.get("deleted", False)),
        )


@dataclass(slots=True)
class PollOption:
    id: str = ""
    text: str = ""
    emoji: str | None = None
    count: int = 0

    @classmethod
    def from_dict(cls, data: dict | None) -> PollOption:
        data = data or {}
        return cls(
            id=data.get("id", ""),
            text=data.get("text", ""),
            emoji=data.get("emoji"),
            count=data.get("count", 0),
        )


@dataclass(slots=True)
class Poll:
    message_id: str = ""
    question: str = ""
    allow_multiple: bool = False
    closes_at: str | None = None
    closed_at: str | None = None
    source: str = "harmony"
    options: list[PollOption] = field(default_factory=list)
    total_voters: int = 0
    my_votes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict | None) -> Poll:
        data = data or {}
        return cls(
            message_id=data.get("messageId", ""),
            question=data.get("question", ""),
            allow_multiple=bool(data.get("allowMultiple", False)),
            closes_at=data.get("closesAt"),
            closed_at=data.get("closedAt"),
            source=data.get("source", "harmony"),
            options=_list(data.get("options"), PollOption.from_dict),
            total_voters=data.get("totalVoters", 0),
            my_votes=list(data.get("myVotes") or []),
        )

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None


@dataclass(slots=True)
class Message:
    id: str = ""
    channel_id: str = ""
    author: User | None = None
    content: str = ""
    created_at: str | None = None
    edited_at: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    reply_to: MessageReference | None = None
    reactions: list[Reaction] = field(default_factory=list)
    pinned_at: str | None = None
    saved: bool = False
    poll: Poll | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> Message:
        data = data or {}
        author = data.get("author")
        reply_to = data.get("replyTo")
        poll = data.get("poll")
        return cls(
            id=data.get("id", ""),
            channel_id=data.get("channelId", ""),
            author=User.from_dict(author) if author else None,
            content=data.get("content", ""),
            created_at=data.get("createdAt"),
            edited_at=data.get("editedAt"),
            attachments=_list(data.get("attachments"), Attachment.from_dict),
            reply_to=MessageReference.from_dict(reply_to) if reply_to else None,
            reactions=_list(data.get("reactions"), Reaction.from_dict),
            pinned_at=data.get("pinnedAt"),
            saved=bool(data.get("saved", False)),
            poll=Poll.from_dict(poll) if poll else None,
        )

    @property
    def is_edited(self) -> bool:
        return self.edited_at is not None


@dataclass(slots=True)
class Role:
    id: str = ""
    name: str = ""
    color: int | None = None
    position: int = 0
    permissions: Permissions = Permissions.NONE
    hoist: bool = False
    mentionable: bool = False
    is_default: bool = False
    badge: str = "none"

    @classmethod
    def from_dict(cls, data: dict | None) -> Role:
        data = data or {}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            color=data.get("color"),
            position=data.get("position", 0),
            permissions=Permissions.from_value(data.get("permissions", "0")),
            hoist=bool(data.get("hoist", False)),
            mentionable=bool(data.get("mentionable", False)),
            is_default=bool(data.get("isDefault", False)),
            badge=data.get("badge", "none"),
        )

    def __str__(self) -> str:
        return self.name


@dataclass(slots=True)
class Member:
    user: User = field(default_factory=User)
    role_ids: list[str] = field(default_factory=list)
    permissions: Permissions = Permissions.NONE
    online: bool | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> Member:
        data = data or {}
        return cls(
            user=User.from_dict(data.get("user")),
            role_ids=list(data.get("roleIds") or []),
            permissions=Permissions.from_value(data.get("permissions", "0")),
            online=data.get("online"),
        )

    @property
    def id(self) -> str:
        return self.user.id

    @property
    def name(self) -> str:
        return self.user.name

    def __str__(self) -> str:
        return self.user.name


@dataclass(slots=True)
class Ban:
    user: User = field(default_factory=User)
    banned_by: User | None = None
    reason: str | None = None
    created_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict | None) -> Ban:
        data = data or {}
        banned_by = data.get("bannedBy")
        return cls(
            user=User.from_dict(data.get("user")),
            banned_by=User.from_dict(banned_by) if banned_by else None,
            reason=data.get("reason"),
            created_at=data.get("createdAt"),
        )


@dataclass(slots=True)
class Emoji:
    id: str = ""
    name: str = ""
    hash: str = ""
    animated: bool = False
    external: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> Emoji:
        data = data or {}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            hash=data.get("hash", ""),
            animated=bool(data.get("animated", False)),
            external=bool(data.get("external", False)),
        )

    @property
    def mention(self) -> str:
        return f":{self.name}:"


# --- Gateway payloads -----------------------------------------------------
# Not "object shapes" from the API, but the `d` of the dispatch events a bot
# cares about. They are modelled so listeners receive typed values.


@dataclass(slots=True)
class MessageDelete:
    id: str = ""
    channel_id: str = ""

    @classmethod
    def from_dict(cls, data: dict | None) -> MessageDelete:
        data = data or {}
        return cls(id=data.get("id", ""), channel_id=data.get("channelId", ""))


@dataclass(slots=True)
class ReactionUpdate:
    message_id: str = ""
    channel_id: str = ""
    emoji: str = ""
    emoji_id: str | None = None
    user_id: str = ""
    count: int = 0

    @classmethod
    def from_dict(cls, data: dict | None) -> ReactionUpdate:
        data = data or {}
        return cls(
            message_id=data.get("messageId", ""),
            channel_id=data.get("channelId", ""),
            emoji=data.get("emoji", ""),
            emoji_id=data.get("emojiId"),
            user_id=data.get("userId", ""),
            count=data.get("count", 0),
        )


@dataclass(slots=True)
class TypingStart:
    channel_id: str = ""
    user: User = field(default_factory=User)

    @classmethod
    def from_dict(cls, data: dict | None) -> TypingStart:
        data = data or {}
        return cls(channel_id=data.get("channelId", ""), user=User.from_dict(data.get("user")))


@dataclass(slots=True)
class PresenceUpdate:
    user: User = field(default_factory=User)
    online: bool = False

    @classmethod
    def from_dict(cls, data: dict | None) -> PresenceUpdate:
        data = data or {}
        return cls(user=User.from_dict(data.get("user")), online=bool(data.get("online", False)))


@dataclass(slots=True)
class CommandInvoke:
    """A member ran one of this bot's slash commands (gateway `COMMAND_INVOKE`)."""

    interaction_id: str = ""
    command_id: str = ""
    name: str = ""
    args: str = ""
    channel_id: str = ""
    user_id: str = ""
    username: str = ""

    @classmethod
    def from_dict(cls, data: dict | None) -> CommandInvoke:
        data = data or {}
        return cls(
            interaction_id=data.get("interactionId", ""),
            command_id=data.get("commandId", ""),
            name=data.get("name", ""),
            args=data.get("args", ""),
            channel_id=data.get("channelId", ""),
            user_id=data.get("userId", ""),
            username=data.get("username", ""),
        )
