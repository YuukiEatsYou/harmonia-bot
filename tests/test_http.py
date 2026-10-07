import pytest
from aiohttp import web

from harmonia.http import HTTPClient


@pytest.fixture
async def fake_server():
    """A throwaway server that records the Content-Type it received per path."""
    seen: dict[str, str | None] = {}

    async def handler(request: web.Request) -> web.Response:
        seen[request.path] = request.headers.get("Content-Type")
        if request.path.endswith("/messages"):
            return web.json_response({"id": "m1", "channelId": "c1", "content": "hi"})
        if request.path.endswith("/roles"):
            return web.json_response({"roles": []})
        if request.path == "/api/v1/auth/me":
            return web.json_response({"user": {"id": "u1", "username": "bot"}, "permissions": "0"})
        return web.json_response({})

    app = web.Application()
    app.router.add_route("*", "/api/v1/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    port = runner.addresses[0][1]
    try:
        yield seen, f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


async def test_bodyless_post_sends_no_content_type(fake_server):
    # aiohttp would otherwise stamp application/octet-stream, which the server
    # rejects with 415 for routes that take no body (kick, typing, ...).
    seen, url = fake_server
    http = HTTPClient(url, "t")
    await http.set_typing("c1")
    await http.kick_member("u1")
    await http.close()
    assert seen["/api/v1/channels/c1/typing"] is None
    assert seen["/api/v1/members/u1/kick"] is None


async def test_json_post_keeps_its_content_type(fake_server):
    seen, url = fake_server
    http = HTTPClient(url, "t")
    await http.send_message("c1", "hi")
    await http.close()
    assert seen["/api/v1/channels/c1/messages"] == "application/json"


async def test_get_does_not_send_a_content_type(fake_server):
    seen, url = fake_server
    http = HTTPClient(url, "t")
    await http.get_roles()
    await http.close()
    assert seen["/api/v1/roles"] is None
