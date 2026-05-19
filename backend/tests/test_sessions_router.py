import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


async def _signup_login(c, email="a@x.com"):
    await c.post("/auth/signup", json={"email": email, "password": "Passw0rd!", "real_name": "Ada"})
    r = await c.post("/auth/login", json={"email": email, "password": "Passw0rd!"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_create_session_returns_id_and_defaults():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        r = await c.post("/sessions", json={"project_title": "Payments"}, headers=h)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["project_title"] == "Payments"
        assert body["status"] == "active"
        assert body["phase"] == "exploration"
        assert body["id"]


@pytest.mark.asyncio
async def test_list_only_returns_user_sessions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token_a = await _signup_login(c, "a@x.com")
        token_b = await _signup_login(c, "b@x.com")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}
        sid_a = (await c.post("/sessions", json={"project_title": "A"}, headers=ha)).json()["id"]
        sid_b = (await c.post("/sessions", json={"project_title": "B"}, headers=hb)).json()["id"]
        a_list = (await c.get("/sessions", headers=ha)).json()
        b_list = (await c.get("/sessions", headers=hb)).json()
        assert [s["id"] for s in a_list] == [sid_a]
        assert [s["id"] for s in b_list] == [sid_b]


@pytest.mark.asyncio
async def test_archive_session_updates_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "X"}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/archive", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "archived"


@pytest.mark.asyncio
async def test_unauthorised_requests_get_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.post("/sessions", json={"project_title": "X"})).status_code == 401
        assert (await c.get("/sessions")).status_code == 401
