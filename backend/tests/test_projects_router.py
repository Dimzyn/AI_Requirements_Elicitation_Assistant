import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_token(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    db = get_db()
    await db.users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    return (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]


@pytest.mark.asyncio
async def test_re_creates_and_lists_own_projects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        tok = await _re_token(c)
        h = {"Authorization": f"Bearer {tok}"}
        r = await c.post("/projects", json={"title": "Hospital", "background": "b"}, headers=h)
        assert r.status_code == 201
        pid = r.json()["id"]
        r = await c.get("/projects", headers=h)
        assert [p["id"] for p in r.json()] == [pid]


@pytest.mark.asyncio
async def test_stakeholder_cannot_create_project():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/auth/signup", json={"email": "s@x.com", "password": "Passw0rd!", "real_name": "S"})
        tok = (await c.post("/auth/login", json={"email": "s@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.post("/projects", json={"title": "X"}, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_project_roundtrip_and_wrong_owner_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        tok = await _re_token(c)
        h = {"Authorization": f"Bearer {tok}"}
        pid = (await c.post("/projects", json={"title": "Hospital"}, headers=h)).json()["id"]

        r = await c.get(f"/projects/{pid}", headers=h)
        assert r.status_code == 200
        assert r.json()["id"] == pid
        assert r.json()["title"] == "Hospital"

        # a different RE must not see someone else's project
        await c.post("/auth/signup", json={"email": "re2@x.com", "password": "Passw0rd!", "real_name": "RE2"})
        await get_db().users.update_one({"email": "re2@x.com"}, {"$set": {"role": "requirements_engineer"}})
        tok2 = (await c.post("/auth/login", json={"email": "re2@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.get(f"/projects/{pid}", headers={"Authorization": f"Bearer {tok2}"})
        assert r.status_code == 404
