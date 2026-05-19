from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from ..db.mongo import get_db
from ..deps import current_user_id_from_token
from ..services.export_service import compile_markdown

router = APIRouter(prefix="/sessions", tags=["export"])


@router.get("/{sid}/export", response_class=PlainTextResponse)
async def export_session(
    sid: str,
    format: str = Query(default="md", pattern="^(md|txt)$"),
    user_id: str = Depends(current_user_id_from_token),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    s = await db.sessions.find_one({"_id": oid, "user_id": user_id})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    reqs = [r async for r in db.requirements.find({"session_id": sid})]
    md = compile_markdown(project_title=s["project_title"], requirements=reqs)
    if format == "txt":
        return md.replace("#", "").strip()
    return md
