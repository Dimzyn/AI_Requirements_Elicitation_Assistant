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
async def test_create_without_title_uses_placeholder_and_seeds_greeting():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        r = await c.post("/sessions", json={}, headers=h)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["project_title"] == "New conversation"
        # the AI greeting is seeded as the first turn so the chat is never blank
        turns = (await c.get(f"/sessions/{body['id']}/turns", headers=h)).json()
        assert len(turns) == 1
        assert turns[0]["role"] == "agent"
        assert turns[0]["strategy"] is None
        assert turns[0]["content"]


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


@pytest.mark.asyncio
async def test_unarchive_flips_status_back_to_active():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "X"}, headers=h)).json()["id"]
        await c.post(f"/sessions/{sid}/archive", headers=h)
        r = await c.post(f"/sessions/{sid}/unarchive", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "active"


@pytest.mark.asyncio
async def test_delete_requires_archived_status():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "X"}, headers=h)).json()["id"]
        # active session cannot be deleted
        r = await c.delete(f"/sessions/{sid}", headers=h)
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_cascades_turns_and_requirements():
    from app.db.mongo import get_db
    from datetime import datetime
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "X"}, headers=h)).json()["id"]
        # seed turns + requirements directly
        db = get_db()
        await db.turns.insert_many([
            {"session_id": sid, "role": "stakeholder", "content": "x", "created_at": datetime.utcnow()},
            {"session_id": sid, "role": "agent", "content": "y", "strategy": "concept", "created_at": datetime.utcnow()},
        ])
        await db.requirements.insert_one({
            "session_id": sid, "statement": "Do something.", "type": "functional",
            "source_turn_id": "anything", "created_at": datetime.utcnow(),
        })
        # archive first, then delete
        await c.post(f"/sessions/{sid}/archive", headers=h)
        r = await c.delete(f"/sessions/{sid}", headers=h)
        assert r.status_code == 204
        # everything gone
        assert (await db.turns.count_documents({"session_id": sid})) == 0
        assert (await db.requirements.count_documents({"session_id": sid})) == 0
        from bson import ObjectId
        assert await db.sessions.find_one({"_id": ObjectId(sid)}) is None


@pytest.mark.asyncio
async def test_delete_404_for_other_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        ta = await _signup_login(c, "a@x.com")
        tb = await _signup_login(c, "b@x.com")
        sid = (await c.post("/sessions", json={"project_title": "A"}, headers={"Authorization": f"Bearer {ta}"})).json()["id"]
        await c.post(f"/sessions/{sid}/archive", headers={"Authorization": f"Bearer {ta}"})
        r = await c.delete(f"/sessions/{sid}", headers={"Authorization": f"Bearer {tb}"})
        assert r.status_code == 404
