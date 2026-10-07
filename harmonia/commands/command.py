"""The `Command` object and the `@command` decorator.

A decorated function becomes a `Command`. On a `Cog` it is a class attribute and
works as a descriptor: accessing it through an instance returns a copy whose
callback is bound to that instance, which is how a command's `self` resolves to
its cog.

The first parameter of the callback is always the `Context`; the rest are bound
from the argument string using the converter matching each annotation.
"""

from __future__ import annotations

import copy
import inspect
import typing
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..errors import BadArgument, MissingRequiredArgument
from ..permissions import Permissions
from . import converters
from .parser import split_flags, tokenize

_KIND = {
    inspect.Parameter.POSITIONAL_ONLY: "positional",
    inspect.Parameter.POSITIONAL_OR_KEYWORD: "positional",
    inspect.Parameter.VAR_POSITIONAL: "var_positional",
    inspect.Parameter.KEYWORD_ONLY: "keyword",
    inspect.Parameter.VAR_KEYWORD: "var_keyword",
}


@dataclass(slots=True)
class Parameter:
    name: str
    kind: str
    annotation: Any
    default: Any
    required: bool


def _parse_parameters(callback: Callable) -> list[Parameter]:
    signature = inspect.signature(callback)
    try:
        hints = typing.get_type_hints(callback)
    except Exception:  # noqa: BLE001 - unresolved names fall back to the raw annotation
        hints = {}

    parameters: list[Parameter] = []
    for index, param in enumerate(signature.parameters.values()):
        if index == 0:  # the context
            continue
        annotation = hints.get(param.name, param.annotation)
        kind = _KIND.get(param.kind, "positional")
        required = param.default is inspect.Parameter.empty and kind in ("positional", "keyword")
        parameters.append(Parameter(param.name, kind, annotation, param.default, required))
    return parameters


class Command:
    """A slash command offered to the server, and how to run it."""

    def __init__(
        self,
        callback: Callable,
        *,
        name: str,
        description: str = "",
        required_permissions: Permissions = Permissions.NONE,
        checks: list | None = None,
    ) -> None:
        if not name:
            raise ValueError("a command needs a name")
        self.callback = callback
        self.name = name
        self.description = description
        self.required_permissions = required_permissions
        self.checks = list(checks or [])
        self.cog: Any = None
        self.id: str | None = None
        self.parameters: list[Parameter] = _parse_parameters(callback)

    def __get__(self, instance: Any, owner: type | None = None) -> Command:
        if instance is None:
            return self
        bound = copy.copy(self)
        bound.callback = self.callback.__get__(instance, owner)
        bound.cog = instance
        bound.parameters = _parse_parameters(bound.callback)
        return bound

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.callback(*args, **kwargs)

    @property
    def signature(self) -> str:
        """A readable parameter list for help output."""
        parts = []
        for param in self.parameters:
            resolved, _ = converters._resolve(param.annotation)
            if param.kind == "var_positional":
                parts.append(f"[{param.name}...]")
            elif param.kind == "keyword" and param.default is inspect.Parameter.empty:
                if resolved is str:
                    parts.append(f"[{param.name}...]")
                else:
                    parts.append(f"<--{param.name}=...>")
            elif param.kind == "keyword":
                parts.append(f"[--{param.name}=...]")
            elif param.required:
                parts.append(f"<{param.name}>")
            else:
                parts.append(f"[{param.name}]")
        return " ".join(parts)

    def to_registration(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "requiredPermissions": self.required_permissions.to_value(),
        }

    async def run_checks(self, ctx) -> None:
        for item in self.checks:
            await item(ctx)

    async def invoke(self, ctx, raw_args: str) -> None:
        """Parse `raw_args` against the signature and run the callback.

        Positional parameters take one token each. A var-positional parameter
        collects the remaining tokens (as Python does). A keyword-only `str`
        parameter with no default consumes the whole remainder as one string,
        which is the idiom for free text such as an incident reason. Every other
        keyword-only parameter is a `--name=value` option.
        """
        positional_tokens, flags = split_flags(tokenize(raw_args))

        positional = [p for p in self.parameters if p.kind == "positional"]
        var_positional = next((p for p in self.parameters if p.kind == "var_positional"), None)
        keyword = [p for p in self.parameters if p.kind == "keyword"]
        var_keyword = next((p for p in self.parameters if p.kind == "var_keyword"), None)
        rest = next(
            (
                p
                for p in keyword
                if p.default is inspect.Parameter.empty
                and converters._resolve(p.annotation)[0] is str
            ),
            None,
        )

        args: list[Any] = [ctx]
        index = 0
        for param in positional:
            if index < len(positional_tokens):
                token = positional_tokens[index]
                index += 1
                args.append(await converters.convert(ctx, param.annotation, token, name=param.name))
            elif param.default is not inspect.Parameter.empty:
                args.append(param.default)
            else:
                raise MissingRequiredArgument(param.name)

        kwargs: dict[str, Any] = {}
        if rest is not None:
            kwargs[rest.name] = " ".join(positional_tokens[index:])
            index = len(positional_tokens)
        elif var_positional is not None:
            for token in positional_tokens[index:]:
                args.append(
                    await converters.convert(
                        ctx, var_positional.annotation, token, name=var_positional.name
                    )
                )
            index = len(positional_tokens)
        elif index < len(positional_tokens):
            raise BadArgument(f"unexpected extra argument: {' '.join(positional_tokens[index:])}")

        for param in keyword:
            if rest is not None and param is rest:
                continue
            if param.name in flags:
                value = flags.pop(param.name)
                kwargs[param.name] = await converters.convert(
                    ctx, param.annotation, value, name=param.name
                )
            elif param.default is not inspect.Parameter.empty:
                kwargs[param.name] = param.default
            elif converters._resolve(param.annotation)[0] is bool:
                kwargs[param.name] = False
            else:
                raise MissingRequiredArgument(param.name)

        if var_keyword is not None:
            kwargs.update(flags)
        elif flags:
            raise BadArgument(f"unknown option: --{next(iter(flags))}")

        await self.callback(*args, **kwargs)


def command(
    *,
    name: str,
    description: str = "",
    required_permissions: Permissions = Permissions.NONE,
    checks: list | None = None,
) -> Callable[[Callable], Command]:
    """Turn a function into a slash command.

    `required_permissions` is enforced by the server before the invocation ever
    reaches the bot, so it is the first line of access control.
    """

    def decorate(func: Callable) -> Command:
        return Command(
            func,
            name=name,
            description=description,
            required_permissions=Permissions.from_value(required_permissions),
            checks=checks,
        )

    return decorate
