import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_project_and_invited_stakeholder(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    re_tok = (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]
    reh = {"Authorization": f"Bearer {re_tok}"}
    pid = (await c.post("/projects", json={"title": "P"}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "S"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    return reh, sh, pid


@pytest.mark.asyncio
async def test_stakeholder_get_or_create_single_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        r1 = await c.post(f"/projects/{pid}/session", headers=sh)
        assert r1.status_code in (200, 201)
        sid = r1.json()["id"]
        r2 = await c.post(f"/projects/{pid}/session", headers=sh)
        assert r2.json()["id"] == sid


@pytest.mark.asyncio
async def test_non_member_cannot_open_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        await c.post("/auth/signup", json={"email": "out@x.com", "password": "Passw0rd!", "real_name": "O"})
        out_tok = (await c.post("/auth/login", json={"email": "out@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.post(f"/projects/{pid}/session", headers={"Authorization": f"Bearer {out_tok}"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_re_lists_sessions_in_owned_project():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        await c.post(f"/projects/{pid}/session", headers=sh)
        r = await c.get(f"/projects/{pid}/sessions", headers=reh)
        assert r.status_code == 200
        assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_re_completes_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
        r = await c.post(f"/sessions/{sid}/complete", headers=reh)
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
