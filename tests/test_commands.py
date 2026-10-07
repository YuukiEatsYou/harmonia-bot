from types import SimpleNamespace

import pytest

from harmonia.commands.command import command
from harmonia.errors import BadArgument, MissingRequiredArgument
from harmonia.models import Member, User


class FakeBot:
    def __init__(self, members=None):
        self._members = members or {}

    async def resolve_member(self, value):
        return self._members.get(value)

    async def resolve_user(self, value):
        return None

    async def resolve_channel(self, value):
        return None

    async def resolve_role(self, value):
        return None


def ctx_for(bot=None):
    return SimpleNamespace(bot=bot or FakeBot())


async def test_positionals_are_converted():
    seen = {}

    @command(name="add")
    async def add(ctx, a: int, b: int):
        seen["sum"] = a + b

    await add.invoke(ctx_for(), "2 3")
    assert seen["sum"] == 5


async def test_missing_required_argument():
    @command(name="add")
    async def add(ctx, a: int, b: int):
        pass

    with pytest.raises(MissingRequiredArgument):
        await add.invoke(ctx_for(), "1")


async def test_keyword_flag_with_spaces():
    seen = {}

    @command(name="kick")
    async def kick(ctx, member: str, *, reason: str = ""):
        seen.update(member=member, reason=reason)

    await kick.invoke(ctx_for(), 'bob --reason="was being rude"')
    assert seen == {"member": "bob", "reason": "was being rude"}


async def test_var_positional_collects_tokens():
    seen = {}

    @command(name="say")
    async def say(ctx, *text: str):
        seen["text"] = text

    await say.invoke(ctx_for(), "hello there world")
    assert seen["text"] == ("hello", "there", "world")


async def test_rest_string_consumes_the_remainder():
    seen = {}

    @command(name="say")
    async def say(ctx, *, text: str):
        seen["text"] = text

    await say.invoke(ctx_for(), "hello there world")
    assert seen["text"] == "hello there world"


async def test_var_positional_keeps_quoted_tokens():
    seen = {}

    @command(name="poll")
    async def poll(ctx, question: str, *options: str):
        seen.update(question=question, options=options)

    await poll.invoke(ctx_for(), '"Pizza?" "Pizza" "Deep dish"')
    assert seen == {"question": "Pizza?", "options": ("Pizza", "Deep dish")}


async def test_boolean_flag_defaults_false():
    seen = {}

    @command(name="poll")
    async def poll(ctx, question: str, *options: str, multiple: bool = False):
        seen["multiple"] = multiple

    await poll.invoke(ctx_for(), '"Q" A B')
    assert seen["multiple"] is False
    await poll.invoke(ctx_for(), '"Q" A B --multiple')
    assert seen["multiple"] is True


async def test_unknown_flag_is_rejected():
    @command(name="x")
    async def x(ctx, a: str):
        pass

    with pytest.raises(BadArgument):
        await x.invoke(ctx_for(), "one --nope")


async def test_extra_positional_is_rejected():
    @command(name="x")
    async def x(ctx, a: str):
        pass

    with pytest.raises(BadArgument):
        await x.invoke(ctx_for(), "one two")


async def test_default_used_when_omitted():
    seen = {}

    @command(name="x")
    async def x(ctx, a: str = "fallback"):
        seen["a"] = a

    await x.invoke(ctx_for(), "")
    assert seen["a"] == "fallback"


async def test_member_converter_uses_bot_lookup():
    member = Member(user=User.from_dict({"id": "u1", "username": "bob"}))
    seen = {}

    @command(name="kick")
    async def kick(ctx, member: Member):
        seen["member"] = member

    await kick.invoke(ctx_for(FakeBot(members={"bob": member})), "bob")
    assert seen["member"].user.username == "bob"


async def test_member_converter_failure_is_user_input_error():
    @command(name="kick")
    async def kick(ctx, member: Member):
        pass

    with pytest.raises(BadArgument):
        await kick.invoke(ctx_for(FakeBot()), "nobody")


async def test_registration_shape():
    @command(
        name="ban",
        description="Ban a member",
        required_permissions=__import__("harmonia").Permissions.BAN_MEMBERS,
    )
    async def ban(ctx, member: str):
        pass

    registration = ban.to_registration()
    assert registration["name"] == "ban"
    assert registration["description"] == "Ban a member"
    assert registration["requiredPermissions"] == str(1 << 11)
