from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from ..db.mongo import get_db
from ..deps import current_user_doc, require_engineer
from ..models.invitation import InvitationStatus
from ..schemas.project import InviteCreate, InviteOut, MemberOut, ProjectCreate, ProjectOut
from ..services.invite_service import accept_url_for, new_token

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


@router.get("/mine/memberships", response_model=list[ProjectOut])
async def my_member_projects(user: dict = Depends(current_user_doc)):
    db = get_db()
    out: list[ProjectOut] = []
    async for m in db.memberships.find({"user_id": user["_id"]}):
        try:
            p = await db.projects.find_one({"_id": ObjectId(m["project_id"])})
        except Exception:
            p = None
        if p:
            out.append(_project_out(p))
    return out


@router.get("/{pid}", response_model=ProjectOut)
async def get_project(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    doc = await _owned_project_or_404(db, pid, user["_id"])
    return _project_out(doc)


@router.post("/{pid}/invitations", status_code=201, response_model=InviteOut)
async def invite_stakeholder(pid: str, body: InviteCreate, user: dict = Depends(require_engineer)):
    db = get_db()
    await _owned_project_or_404(db, pid, user["_id"])
    token = new_token()
    now = datetime.now(timezone.utc)
    doc = {
        "project_id": pid,
        "email": str(body.email),
        "token": token,
        "status": InvitationStatus.PENDING.value,
        "expires_at": now + timedelta(days=7),
        "created_at": now,
    }
    res = await db.invitations.insert_one(doc)
    return InviteOut(
        id=str(res.inserted_id),
        email=doc["email"],
        status=doc["status"],
        token=token,
        accept_url=accept_url_for(token),
        expires_at=doc["expires_at"].isoformat(),
    )


@router.get("/{pid}/members", response_model=list[MemberOut])
async def list_members(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    await _owned_project_or_404(db, pid, user["_id"])
    out: list[MemberOut] = []
    async for m in db.memberships.find({"project_id": pid}):
        u = await db.users.find_one({"_id": ObjectId(m["user_id"])})
        if not u:
            continue
        out.append(MemberOut(
            user_id=m["user_id"],
            email=u["email"],
            real_name=u["real_name"],
            joined_at=m["joined_at"].isoformat() if m.get("joined_at") else None,
        ))
    return out
