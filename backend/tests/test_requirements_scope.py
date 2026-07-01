"""Tests for C1: owner-scoped GET /requirements and PATCH /requirements/{rid}."""
import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _create_re(c, email: str):
    """Sign up + promote to RE, return auth headers."""
    await c.post("/auth/signup", json={"email": email, "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": email}, {"$set": {"role": "requirements_engineer"}})
    tok = (await c.post("/auth/login", json={"email": email, "password": "Passw0rd!"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _setup_re_with_requirement(c, re_email: str, stakeholder_email: str):
    """
    Create an RE, project, invite+accept stakeholder, open a session,
    and directly insert a requirement doc tied to that session.
    Returns (re_headers, project_id, session_id, requirement_id).
    """
    reh = await _create_re(c, re_email)

    # Create project
    pid = (await c.post("/projects", json={"title": "Scope Test"}, headers=reh)).json()["id"]

    # Invite + accept stakeholder
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": stakeholder_email}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "S", "job_title": "Stakeholder"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}

    # Open session
    sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]

    # Directly insert a requirement doc
    now = datetime.now(timezone.utc)
    result = await get_db().requirements.insert_one({
        "session_id": sid,
        "statement": "Users shall log in with email.",
        "type": "functional",
        "source_turn_id": "turn-fake-1",
        "created_at": now,
    })
    rid = str(result.inserted_id)

    return reh, pid, sid, rid


@pytest.mark.asyncio
async def test_owning_re_sees_requirement_in_list():
    """Owning RE can see their own requirements in GET /requirements."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, rid = await _setup_re_with_requirement(
            c, "re_scope1@x.com", "sh_scope1@x.com"
        )
        r = await c.get("/requirements", headers=reh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert isinstance(body, list)
        ids = [item["id"] for item in body]
        assert rid in ids


@pytest.mark.asyncio
async def test_other_re_cannot_see_requirement_in_list():
    """A second RE (non-owner) gets an empty list — cannot see another owner's requirements."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, rid = await _setup_re_with_requirement(
            c, "re_scope2@x.com", "sh_scope2@x.com"
        )
        # Create a second RE who owns nothing
        re2h = await _create_re(c, "re_scope2b@x.com")
        r = await c.get("/requirements", headers=re2h)
        assert r.status_code == 200, r.text
        body = r.json()
        ids = [item["id"] for item in body]
        assert rid not in ids


@pytest.mark.asyncio
async def test_owning_re_sees_requirement_filtered_by_session():
    """GET /requirements?session_id=<owned-sid> returns the requirement."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, rid = await _setup_re_with_requirement(
            c, "re_scope3@x.com", "sh_scope3@x.com"
        )
        r = await c.get(f"/requirements?session_id={sid}", headers=reh)
        assert r.status_code == 200, r.text
        body = r.json()
        ids = [item["id"] for item in body]
        assert rid in ids


@pytest.mark.asyncio
async def test_other_re_gets_empty_list_for_unowned_session():
    """GET /requirements?session_id=<unowned-sid> returns [] for the non-owner RE."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, rid = await _setup_re_with_requirement(
            c, "re_scope4@x.com", "sh_scope4@x.com"
        )
        re2h = await _create_re(c, "re_scope4b@x.com")
        r = await c.get(f"/requirements?session_id={sid}", headers=re2h)
        assert r.status_code == 200, r.text
        assert r.json() == []


@pytest.mark.asyncio
async def test_other_re_gets_404_on_patch_of_unowned_requirement():
    """PATCH /requirements/{rid} by a non-owner RE returns 404."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, rid = await _setup_re_with_requirement(
            c, "re_scope5@x.com", "sh_scope5@x.com"
        )
        re2h = await _create_re(c, "re_scope5b@x.com")
        r = await c.patch(f"/requirements/{rid}", json={"status": "approved"}, headers=re2h)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_owning_re_can_patch_own_requirement():
    """PATCH /requirements/{rid} by the owning RE succeeds."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, rid = await _setup_re_with_requirement(
            c, "re_scope6@x.com", "sh_scope6@x.com"
        )
        r = await c.patch(f"/requirements/{rid}", json={"status": "approved"}, headers=reh)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
