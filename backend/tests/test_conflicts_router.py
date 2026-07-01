import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import conflicts as conflicts_mod


class FakeDetector:
    """Returns a fixed list of {requirement_a, requirement_b, explanation} pairs."""

    def __init__(self, pairs):
        self._pairs = pairs

    async def detect(self, requirements):
        return self._pairs


async def _create_re(c, email: str):
    await c.post("/auth/signup", json={"email": email, "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": email}, {"$set": {"role": "requirements_engineer"}})
    tok = (await c.post("/auth/login", json={"email": email, "password": "Passw0rd!"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _setup_project_with_two_reqs(c, re_email, sh_email, sh_name="Alice"):
    """RE + project + one stakeholder session + two requirements in that session.

    Returns (re_headers, project_id, session_id, [rid_a, rid_b]).
    """
    reh = await _create_re(c, re_email)
    pid = (await c.post("/projects", json={"title": "Conflict Test"}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": sh_email}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": sh_name, "job_title": "Stakeholder"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]

    now = datetime.now(timezone.utc)
    rid_a = str((await get_db().requirements.insert_one({
        "session_id": sid, "statement": "Auto-approve all refunds.",
        "type": "functional", "source_turn_id": "t1", "created_at": now,
    })).inserted_id)
    rid_b = str((await get_db().requirements.insert_one({
        "session_id": sid, "statement": "All refunds require manager sign-off.",
        "type": "functional", "source_turn_id": "t2", "created_at": now,
    })).inserted_id)
    return reh, pid, sid, [rid_a, rid_b]


@pytest.mark.asyncio
async def test_detect_stores_and_returns_open_conflicts(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c1@x.com", "sh_c1@x.com", sh_name="Alice"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        item = body[0]
        assert item["status"] == "open"
        assert item["explanation"] == "Cannot coexist."
        statements = {item["requirement_a"]["statement"], item["requirement_b"]["statement"]}
        assert "Auto-approve all refunds." in statements
        # stakeholder name resolved from the session
        assert item["requirement_a"]["stakeholder"] == "Alice"


@pytest.mark.asyncio
async def test_detect_is_idempotent_no_duplicate_rows(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c2@x.com", "sh_c2@x.com"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        count = await get_db().conflicts.count_documents({"project_id": pid})
        assert count == 1


@pytest.mark.asyncio
async def test_detect_requires_sre_role(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c3@x.com", "sh_c3@x.com"
        )
        # log in as the stakeholder
        s_tok = (await c.post("/auth/login", json={"email": "sh_c3@x.com", "password": "Stake123!"})).json()["access_token"]
        sh = {"Authorization": f"Bearer {s_tok}"}
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=sh)
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_detect_on_unowned_project_returns_404(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, _ = await _setup_project_with_two_reqs(
            c, "re_c4@x.com", "sh_c4@x.com"
        )
        re2h = await _create_re(c, "re_c4b@x.com")
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=re2h)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_detect_returns_503_when_llm_unavailable(monkeypatch):
    from app.services.llm_service import UpstreamUnavailable

    class FailingDetector:
        async def detect(self, requirements):
            raise UpstreamUnavailable("Gemini is temporarily overloaded.")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, _ = await _setup_project_with_two_reqs(
            c, "re_c4c@x.com", "sh_c4c@x.com"
        )
        monkeypatch.setattr(conflicts_mod, "_make_detector", lambda: FailingDetector())
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        assert r.status_code == 503, r.text


@pytest.mark.asyncio
async def test_list_conflicts_returns_stored_open_conflicts(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c5@x.com", "sh_c5@x.com"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        r = await c.get(f"/projects/{pid}/conflicts", headers=reh)
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_list_hides_stale_conflict_when_requirement_rejected(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c6@x.com", "sh_c6@x.com"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        # Reject one of the referenced requirements
        await c.patch(f"/requirements/{rid_a}", json={"status": "rejected"}, headers=reh)
        r = await c.get(f"/projects/{pid}/conflicts", headers=reh)
        assert r.status_code == 200, r.text
        assert r.json() == []


@pytest.mark.asyncio
async def test_list_on_unowned_project_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, _ = await _setup_project_with_two_reqs(
            c, "re_c7@x.com", "sh_c7@x.com"
        )
        re2h = await _create_re(c, "re_c7b@x.com")
        r = await c.get(f"/projects/{pid}/conflicts", headers=re2h)
        assert r.status_code == 404, r.text


async def _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch):
    a, b = sorted((rid_a, rid_b))
    monkeypatch.setattr(
        conflicts_mod, "_make_detector",
        lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
    )
    body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
    return body[0]["id"]


@pytest.mark.asyncio
async def test_patch_marks_conflict_resolved(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c8@x.com", "sh_c8@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.patch(f"/conflicts/{cid}", json={"status": "resolved"}, headers=reh)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "resolved"
        # resolved_by is stamped with the engineer's user id
        re_user = await get_db().users.find_one({"email": "re_c8@x.com"})
        doc = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert doc["resolved_by"] == str(re_user["_id"])


@pytest.mark.asyncio
async def test_patch_rejects_invalid_status(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c9@x.com", "sh_c9@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.patch(f"/conflicts/{cid}", json={"status": "open"}, headers=reh)
        assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_patch_on_unowned_conflict_returns_404(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c10@x.com", "sh_c10@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        re2h = await _create_re(c, "re_c10b@x.com")
        r = await c.patch(f"/conflicts/{cid}", json={"status": "dismissed"}, headers=re2h)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_dismissed_conflict_not_reopened_on_redetect(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c11@x.com", "sh_c11@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        await c.patch(f"/conflicts/{cid}", json={"status": "dismissed"}, headers=reh)
        # Re-run detection — the same pair comes back from the detector
        body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
        # open list is empty because the only pair stays dismissed
        assert body == []
        doc = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert doc["status"] == "dismissed"


@pytest.mark.asyncio
async def test_apply_writes_surviving_rejects_counterpart_resolves(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_ap1@x.com", "sh_ap1@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.post(
            f"/conflicts/{cid}/apply",
            json={
                "surviving_requirement_id": rid_a,
                "statement": "Refunds under $50 auto-approve; $50+ need sign-off.",
            },
            headers=reh,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "resolved"
        surv = await get_db().requirements.find_one({"_id": ObjectId(rid_a)})
        ctr = await get_db().requirements.find_one({"_id": ObjectId(rid_b)})
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert surv["statement"].startswith("Refunds under $50")
        assert ctr["status"] == "rejected"
        assert conf["status"] == "resolved"


@pytest.mark.asyncio
async def test_apply_rejects_surviving_id_not_in_conflict(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_ap2@x.com", "sh_ap2@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.post(
            f"/conflicts/{cid}/apply",
            json={"surviving_requirement_id": str(ObjectId()), "statement": "X."},
            headers=reh,
        )
        assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_apply_on_unowned_conflict_returns_404(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_ap3@x.com", "sh_ap3@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        re2h = await _create_re(c, "re_ap3b@x.com")
        r = await c.post(
            f"/conflicts/{cid}/apply",
            json={"surviving_requirement_id": rid_a, "statement": "X."},
            headers=re2h,
        )
        assert r.status_code == 404, r.text
