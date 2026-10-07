"""Checks a command must pass before it runs.

The server already enforces a command's `requiredPermissions` before it is even
delivered to the bot, so these are for the bot's own conditions: whether *the
bot* holds a permission, a custom predicate, and so on. A failed check raises
`CheckFailure`, whose message is sent back to the invoker.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING

from ..errors import CheckFailure
from ..permissions import Permissions

if TYPE_CHECKING:
    from ..context import Context


class Check:
    """Wraps a predicate returning `bool | None | str` into an awaitable check."""

    def __init__(self, func: Callable[[Context], object]) -> None:
        self.func = func

    async def __call__(self, ctx: Context) -> None:
        result = self.func(ctx)
        if inspect.isawaitable(result):
            result = await result
        if result is False:
            raise CheckFailure(str(getattr(self.func, "__doc__", None) or "a check failed"))
        if isinstance(result, str):
            raise CheckFailure(result)


def check(func: Callable[[Context], object]) -> Check:
    """Register a custom check. Return `False` or a message to refuse."""
    return Check(func)


def has_permissions(*permissions: Permissions) -> Check:
    """Require that the *bot itself* holds every one of `permissions`."""

    async def predicate(ctx: Context) -> object:
        if not ctx.bot.permissions.has(*permissions):
            missing = "|".join(str(p) for p in permissions)
            return f"I am missing the {missing} permission for that."
        return True

    return Check(predicate)
