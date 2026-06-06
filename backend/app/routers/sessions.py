from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from ..db.mongo import get_db
from ..deps import current_user_doc, require_engineer, require_stakeholder
from ..schemas.session import SessionOut
from .projects import _owned_project_or_404

router = APIRouter(tags=["sessions"])

GREETING = (
    "Hi! I'm here to help capture what you'd like to build. "
    "What's the project or idea you have in mind?"
)


def _to_out(doc: dict, stakeholder: dict | None = None) -> SessionOut:
    return SessionOut(
        id=str(doc["_id"]),
        project_id=doc["project_id"],
        stakeholder_id=doc["stakeholder_id"],
        title=doc.get("title"),
        status=doc["status"],
        phase=doc["phase"],
        created_at=doc["created_at"].isoformat() if doc.get("created_at") else None,
        stakeholder_name=stakeholder.get("real_name") if stakeholder else None,
        stakeholder_email=stakeholder.get("email") if stakeholder else None,
    )


async def _users_by_id(db, ids: list[str]) -> dict[str, dict]:
    """Resolve a set of stakeholder ids to their user docs in one query."""
    oids = []
    for i in set(ids):
        try:
            oids.append(ObjectId(i))
        except Exception:
            continue
    out: dict[str, dict] = {}
    async for u in db.users.find({"_id": {"$in": oids}}):
        out[str(u["_id"])] = u
    return out


async def _is_member(db, project_id: str, user_id: str) -> bool:
    return bool(await db.memberships.find_one({"project_id": project_id, "user_id": user_id}))


@router.post("/projects/{pid}/session", response_model=SessionOut)
async def open_my_session(pid: str, user: dict = Depends(require_stakeholder)):
    db = get_db()
    if not await _is_member(db, pid, user["_id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member of this project")
    existing = await db.sessions.find_one({"project_id": pid, "stakeholder_id": user["_id"]})
    if existing:
        return _to_out(existing)
    now = datetime.now(timezone.utc)
    doc = {
        "project_id": pid,
        "stakeholder_id": user["_id"],
        "title": None,
        "status": "active",
        "phase": "exploration",
        "summary": None,
        "auto_named": False,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.sessions.insert_one(doc)
    doc["_id"] = res.inserted_id
    await db.turns.insert_one({
        "session_id": str(res.inserted_id),
        "role": "agent",
        "content": GREETING,
        "created_at": now,
    })
    return _to_out(doc)


@router.get("/projects/{pid}/sessions", response_model=list[SessionOut])
async def list_project_sessions(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    await _owned_project_or_404(db, pid, user["_id"])
    docs = [s async for s in db.sessions.find({"project_id": pid}).sort("created_at", -1)]
    users = await _users_by_id(db, [s["stakeholder_id"] for s in docs])
    return [_to_out(s, users.get(s["stakeholder_id"])) for s in docs]


@router.get("/sessions/all", response_model=list[SessionOut])
async def list_all_owned_sessions(user: dict = Depends(require_engineer)):
    db = get_db()
    owned = [str(p["_id"]) async for p in db.projects.find({"owner_id": user["_id"]})]
    docs = [s async for s in db.sessions.find({"project_id": {"$in": owned}}).sort("created_at", -1)]
    users = await _users_by_id(db, [s["stakeholder_id"] for s in docs])
    return [_to_out(s, users.get(s["stakeholder_id"])) for s in docs]


@router.get("/sessions", response_model=list[SessionOut])
async def list_my_sessions(user: dict = Depends(current_user_doc)):
    db = get_db()
    out: list[SessionOut] = []
    async for s in db.sessions.find({"stakeholder_id": user["_id"]}).sort("created_at", -1):
        out.append(_to_out(s))
    return out


@router.post("/sessions/{sid}/complete", response_model=SessionOut)
async def complete_session(sid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    s = await db.sessions.find_one({"_id": oid})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    await _owned_project_or_404(db, s["project_id"], user["_id"])
    s = await db.sessions.find_one_and_update(
        {"_id": oid},
        {"$set": {"status": "completed", "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return _to_out(s)
