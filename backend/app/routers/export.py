from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from ..db.mongo import get_db
from ..deps import current_user_doc
from ..schemas.requirement import RequirementOut
from ..services.export_service import compile_markdown

router = APIRouter(prefix="/sessions", tags=["export"])


def _to_out_req(r: dict) -> RequirementOut:
    return RequirementOut(
        id=str(r["_id"]),
        session_id=r["session_id"],
        statement=r["statement"],
        type=r["type"],
        source_turn_id=r.get("source_turn_id", ""),
        priority=r.get("priority"),
        status=r.get("status", "pending"),
        acceptance_criteria=r.get("acceptance_criteria"),
        edited_by=r.get("edited_by"),
        edited_at=r["edited_at"].isoformat() if r.get("edited_at") else None,
        created_at=r["created_at"],
    )


@router.get("/{sid}/export", response_class=PlainTextResponse)
async def export_session(
    sid: str,
    format: str = Query(default="md", pattern="^(md|txt)$"),
    user: dict = Depends(current_user_doc),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    if user.get("role") == "requirements_engineer":
        s = await db.sessions.find_one({"_id": oid})
    else:
        s = await db.sessions.find_one({"_id": oid, "user_id": user["_id"]})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    reqs = [r async for r in db.requirements.find({"session_id": sid})]
    md = compile_markdown(project_title=s["project_title"], requirements=reqs)
    if format == "txt":
        return md.replace("#", "").strip()
    return md


@router.get("/{sid}/requirements", response_model=list[RequirementOut])
async def list_requirements(
    sid: str,
    user: dict = Depends(current_user_doc),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    if user.get("role") == "requirements_engineer":
        s = await db.sessions.find_one({"_id": oid})
    else:
        s = await db.sessions.find_one({"_id": oid, "user_id": user["_id"]})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    out: list[RequirementOut] = []
    async for r in db.requirements.find({"session_id": sid}).sort("created_at", 1):
        out.append(_to_out_req(r))
    return out
