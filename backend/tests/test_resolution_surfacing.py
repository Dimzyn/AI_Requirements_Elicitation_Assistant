import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import conflicts as conflicts_mod
from tests.helpers import _re_project_and_invited_stakeholder


async def _setup_with_stance(c):
    """Build a conflict + conflict-resolution session and store one captured stance.
    Returns (reh, sh, pid, uid, cid, crid)."""
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
        "resolutions": {uid: {"decision": "a_wins", "statement": "Auto-approve all refunds.",
                              "session_id": "seed", "captured_at": now}},
    })).inserted_id)
    crid = str((await get_db().sessions.insert_one({
        "project_id": pid, "stakeholder_id": uid, "title": "Resolve requirement conflict",
        "kind": "conflict_resolution", "conflict_id": cid, "status": "active", "phase": "validation",
        "summary": "ctx", "auto_named": True, "created_at": now, "updated_at": now,
    })).inserted_id)
    return reh, sh, pid, uid, cid, crid


@pytest.mark.asyncio
async def test_conflict_out_includes_resolutions_with_names():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, uid, cid, crid = await _setup_with_stance(c)
        r = await c.get(f"/projects/{pid}/conflicts", headers=reh)
        assert r.status_code == 200, r.text
        item = r.json()[0]
        assert len(item["resolutions"]) == 1
        stance = item["resolutions"][0]
        assert stance["decision"] == "a_wins"
        assert stance["statement"] == "Auto-approve all refunds."
        assert stance["stakeholder"] == "S"  # real_name from the invited stakeholder


@pytest.mark.asyncio
async def test_resolution_card_includes_my_resolution():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, uid, cid, crid = await _setup_with_stance(c)
        r = await c.get(f"/sessions/{crid}/resolution", headers=sh)
        assert r.status_code == 200, r.text
        card = r.json()
        assert card["my_resolution"]["decision"] == "a_wins"
        assert card["my_resolution"]["statement"] == "Auto-approve all refunds."
