from cogs.moderation import Moderation
from harmonia import Bot, Cog, commands
from harmonia.errors import BadArgument, Forbidden
from harmonia.http import ChannelsSnapshot
from harmonia.models import Member, Message, Role, User


class Echo(Cog):
    @commands.command(name="echo")
    async def echo(self, ctx: commands.Context, *, text: str) -> None:
        await ctx.send(text)

    @commands.command(name="boom")
    async def boom(self, ctx: commands.Context) -> None:
        raise BadArgument("this one always refuses")


def _make_bot(tmp_path) -> Bot:
    return Bot(base_url="http://127.0.0.1:5173", token="t", data_dir=tmp_path)


def _stub_http(bot: Bot) -> dict:
    sent: dict = {}

    async def send_message(channel_id, content=None, *, attachment_ids=None, reply_to=None):
        sent["channel_id"] = channel_id
        sent["content"] = content
        return Message.from_dict({"id": "m1", "channelId": channel_id, "content": content or ""})

    async def get_channels():
        return ChannelsSnapshot()

    async def get_roles():
        return []

    bot.http.send_message = send_message
    bot.http.get_channels = get_channels
    bot.http.get_roles = get_roles
    return sent


def _invoke(name, args):
    return {
        "interactionId": "i1",
        "commandId": "",
        "name": name,
        "args": args,
        "channelId": "c1",
        "userId": "u1",
        "username": "bob",
    }


async def test_command_invoke_reaches_the_cog(tmp_path):
    bot = _make_bot(tmp_path)
    sent = _stub_http(bot)
    await bot.add_cog(Echo(bot))

    await bot._handle_command_invoke(_invoke("echo", "hello there world"))

    assert sent == {"channel_id": "c1", "content": "hello there world"}


async def test_command_error_is_reported_to_the_channel(tmp_path):
    bot = _make_bot(tmp_path)
    sent = _stub_http(bot)
    await bot.add_cog(Echo(bot))

    await bot._handle_command_invoke(_invoke("boom", ""))

    assert sent["channel_id"] == "c1"
    assert sent["content"] == "⚠️ this one always refuses"


async def test_unknown_command_is_ignored(tmp_path):
    bot = _make_bot(tmp_path)
    sent = _stub_http(bot)
    await bot._handle_command_invoke(_invoke("nope", ""))
    assert sent == {}


async def test_ready_sets_user_and_dispatches(tmp_path):
    bot = _make_bot(tmp_path)
    _stub_http(bot)
    seen = []
    bot.listen("ready")(lambda user: seen.append(user))

    await bot._on_dispatch("ready", {"user": {"id": "u1", "username": "bot", "accountType": "bot"}})

    assert bot.user.username == "bot"
    assert bot._ready.is_set()
    assert seen and seen[0].username == "bot"


async def test_message_create_is_modelled_for_listeners(tmp_path):
    bot = _make_bot(tmp_path)
    _stub_http(bot)
    got = []
    bot.listen("message_create")(lambda message: got.append(message))

    await bot._on_dispatch(
        "message_create",
        {"id": "m", "channelId": "c", "author": {"id": "u", "username": "bob"}, "content": "hi"},
    )

    assert got[0].content == "hi"
    assert got[0].author.username == "bob"


async def test_wildcard_listener_sees_every_event(tmp_path):
    bot = _make_bot(tmp_path)
    _stub_http(bot)
    names = []
    bot.listen("*")(lambda payload: names.append(payload))

    await bot._on_dispatch(
        "typing_start", {"channelId": "c", "user": {"id": "u", "username": "bob"}}
    )

    assert names and names[0].channel_id == "c"


async def test_resolve_member_falls_back_to_roster(tmp_path):
    bot = _make_bot(tmp_path)

    async def forbidden():
        raise Forbidden(403, "forbidden", "no")

    async def roster():
        return [Member(user=User.from_dict({"id": "u1", "username": "bob"}), role_ids=["r1"])]

    bot.http.get_members = forbidden
    bot.http.get_roster = roster

    member = await bot.resolve_member("bob")

    assert member.id == "u1"
    assert member.role_ids == ["r1"]


async def test_resolve_member_falls_back_to_directory(tmp_path):
    bot = _make_bot(tmp_path)

    async def forbidden():
        raise Forbidden(403, "forbidden", "no")

    async def directory():
        return [User.from_dict({"id": "u1", "username": "bob"})]

    bot.http.get_members = forbidden
    bot.http.get_roster = forbidden
    bot.http.get_directory = directory

    member = await bot.resolve_member("bob")

    assert member.id == "u1"
    assert member.role_ids == []


async def test_whois_shows_profile_without_manage_roles(tmp_path):
    bot = _make_bot(tmp_path)
    sent = _stub_http(bot)

    async def get_members():
        return [Member(user=User.from_dict({"id": "u1", "username": "bob"}), role_ids=["r1"])]

    async def get_profile(user_id):
        return {
            "bio": "building bots",
            "status": "shipping",
            "socialLinks": {"github": "https://github.com/bob"},
        }

    bot.http.get_members = get_members
    bot.http.get_profile = get_profile
    bot.cache.roles = {"r1": Role.from_dict({"id": "r1", "name": "Moderator"})}
    await bot.add_cog(Moderation(bot))

    await bot._handle_command_invoke(_invoke("whois", "bob"))

    content = sent["content"]
    assert "building bots" in content
    assert "shipping" in content
    assert "https://github.com/bob" in content
    assert "Moderator" in content
