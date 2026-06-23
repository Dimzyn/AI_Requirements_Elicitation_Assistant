from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from ..db.mongo import get_db
from ..deps import current_user_doc, require_engineer, require_stakeholder
from ..schemas.session import SessionOut
from .projects import _owned_project_or_404

router = APIRouter(tags=["sessions"])

def _greeting(real_name: str | None, project_title: str | None) -> str:
    """Warm, personalized opener for a stakeholder's first session turn.

    Falls back gracefully when the name or project title is missing so a
    session can always be greeted.
    """
    first = (real_name or "").strip().split(" ")[0]
    hi = f"Hi {first} 👋" if first else "Hi there 👋"
    if project_title:
        lead = (
            f"You've been brought in to help shape **{project_title}**. "
            "I'm here to capture what *you* need from it"
        )
    else:
        lead = "Glad you're here. I'm here to capture what *you* need"
    return (
        f"{hi} {lead} — the things that'd make your life easier, anything that "
        "frustrates you today, or ideas you've been sitting on. No need for "
        "polished answers; just talk and I'll keep up. So — where should we start?"
    )


def _to_out(doc: dict, stakeholder: dict | None = None) -> SessionOut:
    return SessionOut(
        id=str(doc["_id"]),
        project_id=doc["project_id"],
        stakeholder_id=doc["stakeholder_id"],
        title=doc.get("title"),
        kind=doc.get("kind", "interview"),
        conflict_id=doc.get("conflict_id"),
        status=doc["status"],
        phase=doc["phase"],
        stakeholder_finished=doc.get("stakeholder_finished", False),
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
    # Only the stakeholder's main interview session is unique per project. Exclude
    # conflict-resolution chats (legacy docs have no `kind`, so they read as interview).
    existing = await db.sessions.find_one(
        {"project_id": pid, "stakeholder_id": user["_id"], "kind": {"$ne": "conflict_resolution"}}
    )
    if existing:
        return _to_out(existing)
    now = datetime.now(timezone.utc)
    doc = {
        "project_id": pid,
        "stakeholder_id": user["_id"],
        "title": None,
        "kind": "interview",
        "status": "active",
        "phase": "exploration",
        "summary": None,
        "auto_named": False,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.sessions.insert_one(doc)
    doc["_id"] = res.inserted_id
    project = await db.projects.find_one({"_id": ObjectId(pid)})
    await db.turns.insert_one({
        "session_id": str(res.inserted_id),
        "role": "agent",
        "content": _greeting(user.get("real_name"), project.get("title") if project else None),
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


@router.post("/sessions/{sid}/finish", response_model=SessionOut)
async def finish_my_session(sid: str, user: dict = Depends(require_stakeholder)):
    """Stakeholder signals they're done. Flags the session for RE review without
    ending it — the RE still confirms completion via complete_session."""
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    s = await db.sessions.find_one({"_id": oid, "stakeholder_id": user["_id"]})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    now = datetime.now(timezone.utc)
    s = await db.sessions.find_one_and_update(
        {"_id": oid},
        {"$set": {"stakeholder_finished": True, "finished_at": now, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    return _to_out(s)
