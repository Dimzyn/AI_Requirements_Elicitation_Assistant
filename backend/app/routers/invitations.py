from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status

from ..db.mongo import get_db
from ..models.invitation import InvitationStatus
from ..schemas.invitation import AcceptRequest, AcceptResponse, InvitationView
from ..services.auth_service import create_token, hash_password, verify_password

router = APIRouter(prefix="/invitations", tags=["invitations"])


async def _load_active_invitation(db, token: str) -> dict:
    inv = await db.invitations.find_one({"token": token})
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation not found")
    if inv["status"] == InvitationStatus.ACCEPTED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "invitation already accepted")
    expires_at = inv["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.invitations.update_one({"_id": inv["_id"]}, {"$set": {"status": InvitationStatus.EXPIRED.value}})
        raise HTTPException(status.HTTP_410_GONE, "invitation expired")
    return inv


@router.get("/{token}", response_model=InvitationView)
async def view_invitation(token: str):
    db = get_db()
    inv = await _load_active_invitation(db, token)
    project = await db.projects.find_one({"_id": ObjectId(inv["project_id"])})
    return InvitationView(
        email=inv["email"],
        project_title=project["title"] if project else "(unknown project)",
        status=inv["status"],
    )


@router.post("/{token}/accept", response_model=AcceptResponse)
async def accept_invitation(token: str, body: AcceptRequest):
    db = get_db()
    inv = await _load_active_invitation(db, token)

    user = await db.users.find_one({"email": inv["email"]})
    if user:
        if not verify_password(body.password, user["hashed_password"]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid password for existing account")
        user_id = str(user["_id"])
    else:
        real_name = (body.real_name or "").strip()
        if not real_name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "name required")
        job_title = (body.job_title or "").strip()
        if not job_title:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "role required")
        now = datetime.now(timezone.utc)
        doc = {
            "email": inv["email"],
            "hashed_password": hash_password(body.password),
            "real_name": real_name,
            "job_title": job_title,
            "phone": None,
            "domain_level": "novice",
            "role": "stakeholder",
            "status": "active",
            "created_at": now,
        }
        res = await db.users.insert_one(doc)
        user_id = str(res.inserted_id)

    existing = await db.memberships.find_one({"project_id": inv["project_id"], "user_id": user_id})
    if not existing:
        await db.memberships.insert_one({
            "project_id": inv["project_id"],
            "user_id": user_id,
            "role_in_project": "stakeholder",
            "joined_at": datetime.now(timezone.utc),
        })

    await db.invitations.update_one({"_id": inv["_id"]}, {"$set": {"status": InvitationStatus.ACCEPTED.value}})
    return AcceptResponse(access_token=create_token({"sub": user_id}))
