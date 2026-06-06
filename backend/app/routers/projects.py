from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from ..db.mongo import get_db
from ..deps import require_engineer
from ..schemas.project import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_out(doc: dict) -> ProjectOut:
    return ProjectOut(
        id=str(doc["_id"]),
        title=doc["title"],
        background=doc.get("background"),
        goals=doc.get("goals"),
        scope=doc.get("scope"),
        created_at=doc["created_at"].isoformat() if doc.get("created_at") else None,
    )


async def _owned_project_or_404(db, pid: str, owner_id: str) -> dict:
    try:
        oid = ObjectId(pid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found") from exc
    doc = await db.projects.find_one({"_id": oid, "owner_id": owner_id})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return doc


@router.post("", status_code=201, response_model=ProjectOut)
async def create_project(body: ProjectCreate, user: dict = Depends(require_engineer)):
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "owner_id": user["_id"],
        "title": body.title.strip() or "Untitled Project",
        "background": body.background,
        "goals": body.goals,
        "scope": body.scope,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.projects.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _project_out(doc)


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: dict = Depends(require_engineer)):
    db = get_db()
    out: list[ProjectOut] = []
    async for p in db.projects.find({"owner_id": user["_id"]}).sort("created_at", -1):
        out.append(_project_out(p))
    return out


@router.get("/{pid}", response_model=ProjectOut)
async def get_project(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    doc = await _owned_project_or_404(db, pid, user["_id"])
    return _project_out(doc)
