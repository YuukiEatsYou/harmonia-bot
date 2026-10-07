"""Exceptions raised by the framework.

The HTTP layer maps a failed request to a subclass of `HTTPException` so callers
can catch a specific failure (a missing channel, a permission denial) instead of
inspecting a status code. The command layer has its own small hierarchy under
`CommandError`, whose messages are written to be shown to the person who ran the
command.
"""

from __future__ import annotations

from typing import Any


class HarmonyError(Exception):
    """Base class for every error the framework raises."""


class HTTPException(HarmonyError):
    """The API answered a request with a non-success status.

    Carries the structured error the API returned (`code` and `message`) plus the
    request that produced it, so a log line is enough to understand a failure.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        method: str | None = None,
        path: str | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.method = method
        self.path = path
        location = f"{method} {path}" if method and path else "request"
        super().__init__(f"{location} -> {status} {code}: {message}")


class Unauthorized(HTTPException):
    """401 - the token is missing, expired or invalid."""


class Forbidden(HTTPException):
    """403 - the token is valid but the bot may not do this."""


class NotFound(HTTPException):
    """404 - the target does not exist or is not visible."""


class Conflict(HTTPException):
    """409 - the request clashed with current state (e.g. a name in use)."""


class RateLimited(HTTPException):
    """429 - too many requests; retried by the transport when it can."""


class ServerError(HTTPException):
    """5xx - the server failed to handle an otherwise valid request."""


_STATUS_CLASSES: dict[int, type[HTTPException]] = {
    401: Unauthorized,
    403: Forbidden,
    404: NotFound,
    409: Conflict,
    429: RateLimited,
}


def http_exception_from_response(
    status: int,
    payload: Any,
    *,
    method: str | None = None,
    path: str | None = None,
) -> HTTPException:
    """Build the most specific `HTTPException` for a failed response.

    `payload` is the decoded body if it was JSON, else the raw text. The API
    always answers errors with `{"error": {"code", "message"}}`, but a proxy or a
    crash can return something else, so the shape is treated as a hint.
    """
    code = "unknown"
    message = f"HTTP {status}"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = str(error.get("code", code))
            message = str(error.get("message", message))
    elif isinstance(payload, str) and payload.strip():
        message = payload.strip()

    cls = _STATUS_CLASSES.get(status)
    if cls is None:
        cls = ServerError if status >= 500 else HTTPException
    return cls(status, code, message, method=method, path=path)


class GatewayError(HarmonyError):
    """Something went wrong with the realtime connection."""


class GatewayClosed(GatewayError):
    """The gateway closed the socket with one of its close codes."""

    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"gateway closed ({code}): {reason}")


# --- Command errors -------------------------------------------------------
# A `CommandError` is caught by the framework and its message sent back to the
# channel, so it should read as an explanation to the person who ran the command.


class CommandError(HarmonyError):
    """Base class for failures that should be reported to the invoker."""


class UserInputError(CommandError):
    """The arguments did not make sense."""


class BadArgument(UserInputError):
    """A specific argument could not be converted."""


class MissingRequiredArgument(UserInputError):
    """A required argument was not supplied."""

    def __init__(self, param: str) -> None:
        self.param = param
        super().__init__(f"the '{param}' argument is required")


class CheckFailure(CommandError):
    """A check on the command did not pass."""


class CommandNotFound(CommandError):
    """The invoked command is not registered."""
