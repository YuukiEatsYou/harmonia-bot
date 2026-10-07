"""harmonia - a bot framework for self-hosted Harmony servers.

Build a bot on `Bot`, describe commands with `harmonia.commands`, and package
them into cogs (`harmonia.Cog`). The framework owns the API: REST calls, the
gateway connection, event dispatch, argument parsing and scoped config, so a cog
is just the interesting part.
"""

from __future__ import annotations

from . import commands
from .client import Bot
from .cog import Cog
from .config import CogConfig, Config, ConfigGroup
from .context import Context
from .errors import (
    BadArgument,
    CheckFailure,
    CommandError,
    CommandNotFound,
    Conflict,
    Forbidden,
    GatewayClosed,
    GatewayError,
    HarmonyError,
    HTTPException,
    MissingRequiredArgument,
    NotFound,
    RateLimited,
    ServerError,
    Unauthorized,
    UserInputError,
)
from .models import (
    Attachment,
    Ban,
    Category,
    Channel,
    CommandInvoke,
    Emoji,
    Member,
    Message,
    MessageDelete,
    MessageReference,
    Poll,
    PollOption,
    PresenceUpdate,
    Reaction,
    ReactionUpdate,
    Role,
    TypingStart,
    User,
)
from .permissions import Permissions

__version__ = "0.1.0"

__all__ = [
    "Attachment",
    "BadArgument",
    "Ban",
    "Bot",
    "Category",
    "Channel",
    "CheckFailure",
    "Cog",
    "CogConfig",
    "CommandError",
    "CommandInvoke",
    "CommandNotFound",
    "Config",
    "ConfigGroup",
    "Conflict",
    "Context",
    "Emoji",
    "Forbidden",
    "GatewayClosed",
    "GatewayError",
    "HTTPException",
    "HarmonyError",
    "Member",
    "Message",
    "MessageDelete",
    "MessageReference",
    "MissingRequiredArgument",
    "NotFound",
    "Permissions",
    "Poll",
    "PollOption",
    "PresenceUpdate",
    "RateLimited",
    "Reaction",
    "ReactionUpdate",
    "Role",
    "ServerError",
    "TypingStart",
    "Unauthorized",
    "User",
    "UserInputError",
    "commands",
    "__version__",
]
