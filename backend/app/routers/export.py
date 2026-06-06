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


async def _load_session_for_user(db, oid: ObjectId, user: dict):
    """Load a session doc, allowing access if the caller is the stakeholder
    or an RE who owns the session's project.  Raises 404 on any access denial."""
    s = await db.sessions.find_one({"_id": oid})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    caller_id = user["_id"]
    if s.get("stakeholder_id") == caller_id:
        return s

    if user.get("role") == "requirements_engineer":
        project = await db.projects.find_one(
            {"_id": ObjectId(s["project_id"]), "owner_id": caller_id}
        )
        if project:
            return s

    raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")


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
    s = await _load_session_for_user(db, oid, user)

    # Use the project title for the report heading; fall back to session title or sid
    project = await db.projects.find_one({"_id": ObjectId(s["project_id"])})
    report_title = (project or {}).get("title") or s.get("title") or sid

    reqs = [r async for r in db.requirements.find({"session_id": sid})]
    md = compile_markdown(project_title=report_title, requirements=reqs)
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
    await _load_session_for_user(db, oid, user)

    out: list[RequirementOut] = []
    async for r in db.requirements.find({"session_id": sid}).sort("created_at", 1):
        out.append(_to_out_req(r))
    return out
