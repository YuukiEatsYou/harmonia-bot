from types import SimpleNamespace

import pytest

from harmonia.commands.checks import check, has_permissions
from harmonia.errors import CheckFailure
from harmonia.permissions import Permissions as P


class FakeBot:
    def __init__(self, permissions):
        self.permissions = permissions


async def test_has_permissions_passes_for_administrator():
    await has_permissions(P.BAN_MEMBERS)(SimpleNamespace(bot=FakeBot(P.ADMINISTRATOR)))


async def test_has_permissions_fails_when_missing():
    with pytest.raises(CheckFailure):
        await has_permissions(P.BAN_MEMBERS)(SimpleNamespace(bot=FakeBot(P.VIEW_CHANNELS)))


async def test_custom_check_message_is_raised():
    def predicate(ctx):
        return "custom refusal"

    with pytest.raises(CheckFailure, match="custom refusal"):
        await check(predicate)(SimpleNamespace(bot=FakeBot(P.NONE)))


async def test_custom_check_async_predicate():
    async def predicate(ctx):
        return True

    await check(predicate)(SimpleNamespace(bot=FakeBot(P.NONE)))
