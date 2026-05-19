import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_signup_then_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/signup", json={
            "email": "a@x.com", "password": "Passw0rd!", "real_name": "Ada", "phone": "0123"
        })
        assert r.status_code == 201, r.text
        assert "access_token" in r.json()
        r = await c.post("/auth/login", json={"email": "a@x.com", "password": "Passw0rd!"})
        assert r.status_code == 200, r.text
        assert "access_token" in r.json()

@pytest.mark.asyncio
async def test_duplicate_email_conflicts():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        body = {"email": "b@x.com", "password": "Passw0rd!", "real_name": "B"}
        r = await c.post("/auth/signup", json=body)
        assert r.status_code == 201
        r = await c.post("/auth/signup", json=body)
        assert r.status_code == 409

@pytest.mark.asyncio
async def test_login_wrong_password_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post("/auth/signup", json={"email":"c@x.com","password":"Passw0rd!","real_name":"C"})
        r = await c.post("/auth/login", json={"email":"c@x.com","password":"wrong"})
        assert r.status_code == 401
