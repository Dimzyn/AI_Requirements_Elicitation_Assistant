import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_and_project(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    tok = (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = (await c.post("/projects", json={"title": "P"}, headers=h)).json()["id"]
    return h, pid


@pytest.mark.asyncio
async def test_view_then_accept_creates_user_and_membership():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]

        r = await c.get(f"/invitations/{token}")
        assert r.status_code == 200
        assert r.json()["email"] == "s@x.com"
        assert r.json()["project_title"] == "P"

        r = await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "Stan"})
        assert r.status_code == 200
        assert "access_token" in r.json()

        db = get_db()
        u = await db.users.find_one({"email": "s@x.com"})
        assert u["role"] == "stakeholder"
        assert await db.memberships.find_one({"project_id": pid, "user_id": str(u["_id"])})
        inv = await db.invitations.find_one({"token": token})
        assert inv["status"] == "accepted"


@pytest.mark.asyncio
async def test_accept_twice_is_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]
        await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "Stan"})
        r = await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "Stan"})
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_expired_invitation_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]
        await get_db().invitations.update_one(
            {"token": token},
            {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}},
        )
        r = await c.get(f"/invitations/{token}")
        assert r.status_code == 410


@pytest.mark.asyncio
async def test_existing_user_accepts_with_correct_password():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # existing stakeholder account
        await c.post("/auth/signup", json={"email": "s@x.com", "password": "Stake123!", "real_name": "S"})
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]
        r = await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!"})
        assert r.status_code == 200
        assert "access_token" in r.json()
        db = get_db()
        u = await db.users.find_one({"email": "s@x.com"})
        assert await db.memberships.find_one({"project_id": pid, "user_id": str(u["_id"])})


@pytest.mark.asyncio
async def test_existing_user_accept_wrong_password_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/auth/signup", json={"email": "s@x.com", "password": "Stake123!", "real_name": "S"})
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]
        r = await c.post(f"/invitations/{token}/accept", json={"password": "WRONGpass1"})
        assert r.status_code == 401
