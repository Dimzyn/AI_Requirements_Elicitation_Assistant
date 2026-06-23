from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse, Response

from ..db.mongo import get_db
from ..deps import current_user_doc, require_engineer
from ..schemas.requirement import RequirementOut
from ..services.export_service import compile_markdown, compile_srs, compile_srs_pdf, srs_to_text
from .projects import _owned_project_or_404

router = APIRouter(prefix="/sessions", tags=["export"])

# Project-wide SRS export lives under /projects/{pid}/export, so it needs its own
# router (the session export router above is prefixed with /sessions).
projects_router = APIRouter(prefix="/projects", tags=["export"])


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


async def _load_owned_session_for_re(db, oid: ObjectId, user: dict):
    """Load a session doc, allowing access only for an RE who owns the session's project.
    Stakeholders are blocked with 403.  Non-owners get 404."""
    if user.get("role") != "requirements_engineer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires requirements_engineer role")
    s = await db.sessions.find_one({"_id": oid})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    project = await db.projects.find_one({"_id": ObjectId(s["project_id"]), "owner_id": user["_id"]})
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return s


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
    s = await _load_owned_session_for_re(db, oid, user)

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
    await _load_owned_session_for_re(db, oid, user)

    out: list[RequirementOut] = []
    async for r in db.requirements.find({"session_id": sid}).sort("created_at", 1):
        out.append(_to_out_req(r))
    return out


@projects_router.get("/{pid}/export")
async def export_project_srs(
    pid: str,
    format: str = Query(default="md", pattern="^(md|txt|pdf)$"),
    user: dict = Depends(require_engineer),
):
    """Export every non-rejected requirement in a project as an IEEE-830-style SRS."""
    db = get_db()
    project = await _owned_project_or_404(db, pid, user["_id"])

    # Map each session to its stakeholder's display name (one users query, no N+1).
    sessions = [s async for s in db.sessions.find({"project_id": pid})]
    oids: list[ObjectId] = []
    for s in sessions:
        uid = s.get("stakeholder_id")
        if uid:
            try:
                oids.append(ObjectId(uid))
            except Exception:
                pass
    name_by_uid: dict[str, str | None] = {}
    if oids:
        async for u in db.users.find({"_id": {"$in": oids}}):
            name_by_uid[str(u["_id"])] = u.get("real_name")
    session_to_name = {str(s["_id"]): name_by_uid.get(s.get("stakeholder_id")) for s in sessions}

    reqs: list[dict] = []
    if session_to_name:
        async for r in db.requirements.find(
            {"session_id": {"$in": list(session_to_name.keys())}, "status": {"$ne": "rejected"}}
        ).sort("created_at", 1):
            reqs.append(
                {
                    "statement": r.get("statement", ""),
                    "type": r.get("type", "functional"),
                    "stakeholder": session_to_name.get(r["session_id"]),
                    "priority": r.get("priority"),
                    "status": r.get("status"),
                    "acceptance_criteria": r.get("acceptance_criteria"),
                }
            )

    title = project.get("title") or "Untitled Project"
    background = project.get("background")
    scope = project.get("scope") or project.get("goals")

    if format == "pdf":
        pdf_bytes = compile_srs_pdf(
            project_title=title, project_background=background, project_scope=scope, requirements=reqs
        )
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in title).strip("_") or "project"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}_SRS.pdf"'},
        )

    md = compile_srs(
        project_title=title, project_background=background, project_scope=scope, requirements=reqs
    )
    return PlainTextResponse(srs_to_text(md) if format == "txt" else md)
