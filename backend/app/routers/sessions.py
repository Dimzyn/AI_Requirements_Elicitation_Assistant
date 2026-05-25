from bson import ObjectId
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from ..db.mongo import get_db
from ..deps import current_user_id_from_token, current_user_doc
from ..schemas.session import SessionCreate, SessionOut

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _to_out(doc: dict) -> SessionOut:
    return SessionOut(
        id=str(doc["_id"]),
        project_title=doc["project_title"],
        status=doc["status"],
        phase=doc["phase"],
        user_id=doc.get("user_id"),
        created_at=doc["created_at"].isoformat() if doc.get("created_at") else None,
    )


@router.post("", status_code=201, response_model=SessionOut)
async def create_session(body: SessionCreate, user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    now = datetime.utcnow()
    doc = {
        "user_id": user_id,
        "project_title": body.project_title,
        "status": "active",
        "phase": "exploration",
        "summary": None,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.sessions.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _to_out(doc)


@router.get("", response_model=list[SessionOut])
async def list_sessions(user: dict = Depends(current_user_doc)):
    db = get_db()
    query = {} if user.get("role") == "requirements_engineer" else {"user_id": user["_id"]}
    out: list[SessionOut] = []
    async for s in db.sessions.find(query).sort("created_at", -1):
        out.append(_to_out(s))
    return out


@router.post("/{sid}/archive", response_model=SessionOut)
async def archive_session(sid: str, user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    s = await db.sessions.find_one_and_update(
        {"_id": oid, "user_id": user_id},
        {"$set": {"status": "archived", "updated_at": datetime.utcnow()}},
        return_document=ReturnDocument.AFTER,
    )
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return _to_out(s)


@router.post("/{sid}/unarchive", response_model=SessionOut)
async def unarchive_session(sid: str, user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    s = await db.sessions.find_one_and_update(
        {"_id": oid, "user_id": user_id},
        {"$set": {"status": "active", "updated_at": datetime.utcnow()}},
        return_document=ReturnDocument.AFTER,
    )
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return _to_out(s)


@router.delete("/{sid}", status_code=204)
async def delete_session(sid: str, user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    s = await db.sessions.find_one({"_id": oid, "user_id": user_id})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    if s.get("status") != "archived":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "session must be archived before deletion")
    await db.turns.delete_many({"session_id": sid})
    await db.requirements.delete_many({"session_id": sid})
    await db.sessions.delete_one({"_id": oid})
    return None
