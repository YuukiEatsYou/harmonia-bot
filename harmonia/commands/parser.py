"""Tokenizing the raw argument string a Harmony command arrives with.

The server hands a bot whatever the member typed after the command name, as one
string. There are no structured options, so the framework splits it here:

- Whitespace separates tokens, except inside matching single or double quotes.
- `--name=value` sets a named option.
- `--name` (no `=`) is a boolean flag.

Everything else is a positional token, bound to the command's parameters by
`Command.invoke`.
"""

from __future__ import annotations

_QUOTES = "\"'"


def tokenize(raw: str) -> list[str]:
    """Split `raw` into tokens, honoring quotes and keeping empty quotes."""
    tokens: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    started = False

    for char in raw:
        if quote is not None:
            if char == quote:
                quote = None
            else:
                buffer.append(char)
        elif char in _QUOTES:
            quote = char
            started = True
        elif char.isspace():
            if started:
                tokens.append("".join(buffer))
                buffer = []
                started = False
        else:
            buffer.append(char)
            started = True

    if started:
        tokens.append("".join(buffer))
    return tokens


def split_flags(tokens: list[str]) -> tuple[list[str], dict[str, str | bool]]:
    """Separate positional tokens from `--name[=value]` options."""
    positional: list[str] = []
    flags: dict[str, str | bool] = {}
    for token in tokens:
        if token.startswith("--") and len(token) > 2:
            body = token[2:]
            if "=" in body:
                key, value = body.split("=", 1)
                flags[key] = value
            else:
                flags[body] = True
        else:
            positional.append(token)
    return positional, flags
