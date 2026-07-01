import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import dialogue as dialogue_mod
from tests.helpers import _re_project_and_invited_stakeholder


class FakeTracker:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def track(self, **kwargs):
        self.calls += 1
        return self.result


async def _setup_conflict_session(c):
    """RE + project + stakeholder interview session with two reqs + a conflict + a
    conflict-resolution session owned by the stakeholder. Returns (sh, uid, cid, crid)."""
    reh, sh, pid = await _re_project_and_invited_stakeholder(c)
    sh_user = await get_db().users.find_one({"email": "s@x.com"})
    uid = str(sh_user["_id"])
    sid_iv = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
    now = datetime.now(timezone.utc)
    rid_a = str((await get_db().requirements.insert_one({
        "session_id": sid_iv, "statement": "Auto-approve all refunds.",
        "type": "functional", "source_turn_id": "t", "created_at": now,
    })).inserted_id)
    rid_b = str((await get_db().requirements.insert_one({
        "session_id": sid_iv, "statement": "All refunds require manager sign-off.",
        "type": "functional", "source_turn_id": "t", "created_at": now,
    })).inserted_id)
    a, b = sorted((rid_a, rid_b))
    cid = str((await get_db().conflicts.insert_one({
        "project_id": pid, "requirement_a": a, "requirement_b": b, "pair_key": f"{a}:{b}",
        "explanation": "Cannot coexist.", "status": "open",
        "detected_at": now, "updated_at": now, "resolved_by": None,
    })).inserted_id)
    crid = str((await get_db().sessions.insert_one({
        "project_id": pid, "stakeholder_id": uid, "title": "Resolve requirement conflict",
        "kind": "conflict_resolution", "conflict_id": cid, "status": "active", "phase": "validation",
        "summary": "conflict context", "auto_named": True, "created_at": now, "updated_at": now,
    })).inserted_id)
    return sh, uid, cid, crid


@pytest.mark.asyncio
async def test_resolution_reached_captures_stance_and_pauses(monkeypatch):
    monkeypatch.setattr(
        dialogue_mod, "_make_resolution_tracker",
        lambda: FakeTracker({"reached": True, "decision": "a_wins", "statement": "Auto-approve all refunds."}),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        sh, uid, cid, crid = await _setup_conflict_session(c)
        r = await c.post(f"/sessions/{crid}/messages", json={"content": "Let's just auto-approve them."}, headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["wrap_up_suggested"] is True
        assert body["resolution"]["decision"] == "a_wins"
        assert body["resolution"]["statement"] == "Auto-approve all refunds."
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert conf["resolutions"][uid]["decision"] == "a_wins"
        assert conf["resolutions"][uid]["session_id"] == crid
        sess = await get_db().sessions.find_one({"_id": ObjectId(crid)})
        assert sess["wrap_up_suggested"] is True
        # resolution-only: no spec rows minted from the conflict chat
        assert await get_db().requirements.count_documents({"session_id": crid}) == 0


@pytest.mark.asyncio
async def test_resolution_not_reached_stores_nothing(monkeypatch):
    monkeypatch.setattr(
        dialogue_mod, "_make_resolution_tracker",
        lambda: FakeTracker({"reached": False, "decision": None, "statement": None}),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        sh, uid, cid, crid = await _setup_conflict_session(c)
        r = await c.post(f"/sessions/{crid}/messages", json={"content": "I'm not sure yet."}, headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["wrap_up_suggested"] is False
        assert body["resolution"] is None
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert conf.get("resolutions", {}) == {}
