"""Turning argument strings into typed values.

A command declares its parameters with ordinary Python annotations; `convert`
maps an annotation to a converter and turns the matching token into a value.
The lookup converters (user, member, channel, role) are async because they may
go to the API, which is why invocation awaits them.

Annotations may be the real types (resolved with `typing.get_type_hints`) or the
string form produced by `from __future__ import annotations`; both are handled.
"""

from __future__ import annotations

import datetime as _dt
import inspect
import re
import types
import typing
from collections.abc import Awaitable, Callable
from typing import Any, get_args, get_origin

from ..errors import BadArgument
from ..models import Channel, Member, Role, User
from ..permissions import Permissions

if typing.TYPE_CHECKING:
    from ..context import Context

Converter = Callable[..., Awaitable[Any]]
_CONVERTERS: dict[Any, Converter] = {}

# Names the string form of an annotation may use, resolved to the real object.
_BY_NAME: dict[str, Any] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "User": User,
    "Member": Member,
    "Channel": Channel,
    "Role": Role,
    "Permissions": Permissions,
    "timedelta": _dt.timedelta,
    "datetime": _dt.datetime,
}


def converter(annotation: Any) -> Callable[[Converter], Converter]:
    """Register a converter for one annotation."""

    def decorate(func: Converter) -> Converter:
        _CONVERTERS[annotation] = func
        return func

    return decorate


def _resolve(annotation: Any) -> tuple[Any, bool]:
    """Return `(concrete_type, is_optional)` for an annotation."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return str, False
    if isinstance(annotation, str):
        text = annotation.strip()
        optional = text.endswith("| None") or text.startswith("Optional[")
        inner = text.replace("| None", "").strip()
        if inner.startswith("Optional[") and inner.endswith("]"):
            inner = inner[len("Optional[") : -1].strip()
        return _BY_NAME.get(inner, str), optional

    origin = get_origin(annotation)
    union = origin is typing.Union or origin is types.UnionType
    if union:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        optional = len(args) != len(get_args(annotation))
        if len(args) == 1:
            return _resolve(args[0])[0], optional
        return str, optional
    return annotation, False


async def convert(ctx: Context, annotation: Any, value: Any, *, name: str = "value") -> Any:
    """Convert one token for the parameter called `name`."""
    if isinstance(value, bool):
        # A `--flag` with no value arrives as True; leave it for the target type.
        return value
    resolved, optional = _resolve(annotation)
    if optional and value == "":
        return None
    func = _CONVERTERS.get(resolved)
    if func is None:
        return value
    try:
        return await func(ctx, value)
    except BadArgument:
        raise
    except Exception as error:  # noqa: BLE001 - surfaced as user input error
        raise BadArgument(f"'{value}' is not a valid {name}") from error


@converter(int)
async def _to_int(ctx: Context, value: str) -> int:
    return int(value)


@converter(float)
async def _to_float(ctx: Context, value: str) -> float:
    return float(value)


@converter(bool)
async def _to_bool(ctx: Context, value: str) -> bool:
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise BadArgument(f"'{value}' is not a yes/no value")


_DURATION_RE = re.compile(r"^(?P<amount>\d+)\s*(?P<unit>[smhdw]?)$")
_UNIT_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


@converter(_dt.timedelta)
async def _to_timedelta(ctx: Context, value: str) -> _dt.timedelta:
    match = _DURATION_RE.match(value.strip())
    if not match:
        raise BadArgument(f"'{value}' is not a duration like 30s, 10m, 2h or 1d")
    seconds = int(match.group("amount")) * _UNIT_SECONDS[match.group("unit")]
    return _dt.timedelta(seconds=seconds)


@converter(Permissions)
async def _to_permissions(ctx: Context, value: str) -> Permissions:
    text = value.strip()
    if text.isdigit():
        return Permissions.from_value(text)
    combined = Permissions.NONE
    for piece in re.split(r"[|,]", text):
        name = piece.strip().upper()
        if not name:
            continue
        flag = getattr(Permissions, name, None)
        if not isinstance(flag, Permissions):
            raise BadArgument(f"'{piece}' is not a permission name")
        combined |= flag
    return combined


@converter(Channel)
async def _to_channel(ctx: Context, value: str) -> Channel:
    channel = await ctx.bot.resolve_channel(value)
    if channel is None:
        raise BadArgument(f"no channel matches '{value}'")
    return channel


@converter(Role)
async def _to_role(ctx: Context, value: str) -> Role:
    role = await ctx.bot.resolve_role(value)
    if role is None:
        raise BadArgument(f"no role matches '{value}'")
    return role


@converter(User)
async def _to_user(ctx: Context, value: str) -> User:
    user = await ctx.bot.resolve_user(value)
    if user is None:
        raise BadArgument(f"no member matches '{value}'")
    return user


@converter(Member)
async def _to_member(ctx: Context, value: str) -> Member:
    member = await ctx.bot.resolve_member(value)
    if member is None:
        raise BadArgument(f"no member matches '{value}'")
    return member
