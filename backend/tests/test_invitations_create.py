import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_token(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    return (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]


@pytest.mark.asyncio
async def test_re_invites_stakeholder_returns_accept_url():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h = {"Authorization": f"Bearer {await _re_token(c)}"}
        pid = (await c.post("/projects", json={"title": "P"}, headers=h)).json()["id"]
        r = await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "pending"
        assert body["token"] in body["accept_url"]
        assert body["accept_url"].endswith(f"/invite/{body['token']}")


@pytest.mark.asyncio
async def test_list_members_after_accept():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h = {"Authorization": f"Bearer {await _re_token(c)}"}
        pid = (await c.post("/projects", json={"title": "P"}, headers=h)).json()["id"]
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]
        await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "Stan"})
        r = await c.get(f"/projects/{pid}/members", headers=h)
        assert r.status_code == 200
        members = r.json()
        assert len(members) == 1
        assert members[0]["email"] == "s@x.com"
        assert members[0]["real_name"] == "Stan"
