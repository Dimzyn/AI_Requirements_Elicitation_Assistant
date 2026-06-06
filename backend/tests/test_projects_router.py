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
