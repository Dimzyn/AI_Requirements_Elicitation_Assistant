import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db
from app.services.export_service import compile_markdown
from datetime import datetime, timedelta, timezone


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


async def _re_project_and_session(c, project_title="POS"):
    """Create an RE, project, invite + accept stakeholder, open a session.
    Returns (reh, sh, pid, sid) headers and IDs."""
    await c.post("/auth/signup", json={"email": "re_exp@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re_exp@x.com"}, {"$set": {"role": "requirements_engineer"}})
    re_tok = (await c.post("/auth/login", json={"email": "re_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
    reh = {"Authorization": f"Bearer {re_tok}"}
    pid = (await c.post("/projects", json={"title": project_title}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": "sh_exp@x.com"}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "S"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
    return reh, sh, pid, sid


@pytest.mark.asyncio
async def test_export_returns_markdown_for_stakeholder():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c, project_title="POS")
        await get_db().requirements.insert_one({
            "session_id": sid, "statement": "Cashiers can ring up sales.", "type": "functional"
        })
        r = await c.get(f"/sessions/{sid}/export", headers=sh)
        assert r.status_code == 200, r.text
        assert "# Requirements: POS" in r.text
        assert "Cashiers can ring up sales." in r.text


@pytest.mark.asyncio
async def test_export_returns_markdown_for_re():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c, project_title="POS")
        await get_db().requirements.insert_one({
            "session_id": sid, "statement": "Cashiers can ring up sales.", "type": "functional"
        })
        r = await c.get(f"/sessions/{sid}/export", headers=reh)
        assert r.status_code == 200, r.text
        assert "# Requirements: POS" in r.text
        assert "Cashiers can ring up sales." in r.text


@pytest.mark.asyncio
async def test_export_txt_strips_markdown_hashes():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        r = await c.get(f"/sessions/{sid}/export?format=txt", headers=sh)
        assert r.status_code == 200
        assert "#" not in r.text


@pytest.mark.asyncio
async def test_export_404_for_other_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
        await c.post("/auth/signup", json={"email": "outsider_exp@x.com", "password": "Passw0rd!", "real_name": "O"})
        out_tok = (await c.post("/auth/login", json={"email": "outsider_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.get(f"/sessions/{sid}/export", headers={"Authorization": f"Bearer {out_tok}"})
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_export_401_when_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/sessions/507f1f77bcf86cd799439011/export")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_get_requirements_returns_seeded_items():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, sid = await _re_project_and_session(c)
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
        r = await c.get(f"/sessions/{sid}/requirements", headers=sh)
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
        reh, sh, pid, sid = await _re_project_and_session(c)
        await c.post("/auth/signup", json={"email": "outsider2_exp@x.com", "password": "Passw0rd!", "real_name": "O2"})
        out_tok = (await c.post("/auth/login", json={"email": "outsider2_exp@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.get(f"/sessions/{sid}/requirements", headers={"Authorization": f"Bearer {out_tok}"})
        assert r.status_code == 404
