from harmonia.config import Config


async def test_defaults_apply_until_set(tmp_path):
    cog = Config("test", tmp_path).cog("demo")
    cog.register(duration_hours=24)
    server = cog.server()
    assert await server.get("duration_hours") == 24
    await server.set("duration_hours", 48)
    assert await server.get("duration_hours") == 48


async def test_scopes_are_isolated(tmp_path):
    cog = Config("test", tmp_path).cog("demo")
    await cog.channel("c1").set("level", 1)
    await cog.channel("c2").set("level", 2)
    assert await cog.channel("c1").get("level") == 1
    assert await cog.channel("c2").get("level") == 2
    assert await cog.server().get("level") is None


async def test_values_persist_to_disk(tmp_path):
    await Config("test", tmp_path).cog("demo").server().set("x", 5)
    assert await Config("test", tmp_path).cog("demo").server().get("x") == 5


async def test_cogs_do_not_share_a_namespace(tmp_path):
    config = Config("test", tmp_path)
    await config.cog("one").server().set("k", "a")
    await config.cog("two").server().set("k", "b")
    assert await config.cog("one").server().get("k") == "a"
    assert await config.cog("two").server().get("k") == "b"


async def test_all_merges_defaults_over_stored(tmp_path):
    cog = Config("test", tmp_path).cog("demo")
    cog.register(a=1, b=2)
    await cog.server().set("b", 9)
    assert await cog.server().all() == {"a": 1, "b": 9}


async def test_update_and_clear(tmp_path):
    cog = Config("test", tmp_path).cog("demo")
    await cog.server().update(a=1, b=2)
    assert await cog.server().all() == {"a": 1, "b": 2}
    await cog.server().delete("a")
    assert await cog.server().get("a") is None
    await cog.server().clear()
    assert await cog.server().all() == {}
