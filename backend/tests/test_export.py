import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.export_service import compile_markdown


def test_compile_markdown_groups_by_type():
    reqs = [
        {"statement": "Users can log in.", "type": "functional"},
        {"statement": "P95 latency < 5s for 1000-word input.", "type": "non_functional"},
    ]
    md = compile_markdown(project_title="Payments", requirements=reqs)
    assert "# Requirements: Payments" in md
    assert "## Functional Requirements" in md
    assert "Users can log in." in md
    assert "## Non-Functional Requirements" in md
    assert "P95 latency" in md


def test_compile_markdown_skips_empty_buckets():
    md = compile_markdown(project_title="Empty", requirements=[])
    assert md.startswith("# Requirements: Empty")
    assert "## Functional Requirements" not in md


async def _signup_login(c, email="a@x.com"):
    await c.post("/auth/signup", json={"email": email, "password": "Passw0rd!", "real_name": "Ada"})
    r = await c.post("/auth/login", json={"email": email, "password": "Passw0rd!"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_export_returns_markdown_for_owner():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "POS"}, headers=h)).json()["id"]
        # seed requirements directly via the test DB
        from app.db.mongo import get_db
        await get_db().requirements.insert_one({
            "session_id": sid, "statement": "Cashiers can ring up sales.", "type": "functional"
        })
        r = await c.get(f"/sessions/{sid}/export", headers=h)
        assert r.status_code == 200, r.text
        assert "# Requirements: POS" in r.text
        assert "Cashiers can ring up sales." in r.text


@pytest.mark.asyncio
async def test_export_txt_strips_markdown_hashes():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "POS"}, headers=h)).json()["id"]
        r = await c.get(f"/sessions/{sid}/export?format=txt", headers=h)
        assert r.status_code == 200
        assert "#" not in r.text


@pytest.mark.asyncio
async def test_export_404_for_other_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token_a = await _signup_login(c, "a@x.com")
        token_b = await _signup_login(c, "b@x.com")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}
        sid_a = (await c.post("/sessions", json={"project_title": "A"}, headers=ha)).json()["id"]
        r = await c.get(f"/sessions/{sid_a}/export", headers=hb)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_export_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/sessions/507f1f77bcf86cd799439011/export")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_requirements_returns_seeded_items():
    from datetime import datetime, timedelta, timezone
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _signup_login(c)
        h = {"Authorization": f"Bearer {token}"}
        sid = (await c.post("/sessions", json={"project_title": "POS"}, headers=h)).json()["id"]
        from app.db.mongo import get_db
        base = datetime.now(timezone.utc)
        await get_db().requirements.insert_many([
            {
                "session_id": sid,
                "statement": "Cashiers can ring up sales.",
                "type": "functional",
                "source_turn_id": "turn-1",
                "created_at": base,
            },
            {
                "session_id": sid,
                "statement": "P95 latency below 3s.",
                "type": "non_functional",
                "source_turn_id": "turn-1",
                "created_at": base + timedelta(seconds=1),
            },
        ])
        r = await c.get(f"/sessions/{sid}/requirements", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 2
        # ordered by created_at ascending
        assert body[0]["statement"] == "Cashiers can ring up sales."
        assert body[0]["type"] == "functional"
        assert body[0]["source_turn_id"] == "turn-1"
        assert body[0]["created_at"]
        assert body[0]["id"]
        assert body[1]["statement"] == "P95 latency below 3s."
        assert body[1]["type"] == "non_functional"


@pytest.mark.asyncio
async def test_get_requirements_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/sessions/507f1f77bcf86cd799439011/requirements")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_requirements_404_for_other_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token_a = await _signup_login(c, "a@x.com")
        token_b = await _signup_login(c, "b@x.com")
        ha = {"Authorization": f"Bearer {token_a}"}
        hb = {"Authorization": f"Bearer {token_b}"}
        sid_a = (await c.post("/sessions", json={"project_title": "A"}, headers=ha)).json()["id"]
        r = await c.get(f"/sessions/{sid_a}/requirements", headers=hb)
        assert r.status_code == 404
