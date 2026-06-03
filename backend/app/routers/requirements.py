from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from ..db.mongo import get_db
from ..deps import current_user_doc
from ..schemas.requirement import RequirementOut, RequirementPatch

router = APIRouter(prefix="/requirements", tags=["requirements"])

_VALID_PRIORITIES = {"must", "should", "could", "wont"}
_VALID_STATUSES = {"pending", "approved", "rejected", "needs_clarification"}
_VALID_TYPES = {"functional", "non_functional", "constraint"}


def _to_out(doc: dict) -> RequirementOut:
    return RequirementOut(
        id=str(doc["_id"]),
        session_id=doc["session_id"],
        statement=doc["statement"],
        type=doc["type"],
        source_turn_id=doc.get("source_turn_id", ""),
        priority=doc.get("priority"),
        status=doc.get("status", "pending"),
        acceptance_criteria=doc.get("acceptance_criteria"),
        edited_by=doc.get("edited_by"),
        edited_at=doc["edited_at"].isoformat() if doc.get("edited_at") else None,
        created_at=doc["created_at"],
    )


def _require_sre(user: dict):
    if user.get("role") != "requirements_engineer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires requirements_engineer role")


@router.get("", response_model=list[RequirementOut])
async def list_all_requirements(
    session_id: str | None = Query(default=None),
    req_status: str | None = Query(default=None, alias="status"),
    req_type: str | None = Query(default=None, alias="type"),
    user: dict = Depends(current_user_doc),
):
    _require_sre(user)
    db = get_db()
    query: dict = {}
    if session_id:
        query["session_id"] = session_id
    if req_status:
        query["status"] = req_status
    if req_type:
        query["type"] = req_type
    out: list[RequirementOut] = []
    async for r in db.requirements.find(query).sort("created_at", 1):
        out.append(_to_out(r))
    return out


@router.patch("/{rid}", response_model=RequirementOut)
async def patch_requirement(
    rid: str,
    body: RequirementPatch,
    user: dict = Depends(current_user_doc),
):
    _require_sre(user)
    db = get_db()
    try:
        oid = ObjectId(rid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement not found") from exc

    updates: dict = {}
    if body.statement is not None:
        updates["statement"] = body.statement
    if body.type is not None:
        if body.type not in _VALID_TYPES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"type must be one of {_VALID_TYPES}",
            )
        updates["type"] = body.type
    if body.priority is not None:
        if body.priority not in _VALID_PRIORITIES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"priority must be one of {_VALID_PRIORITIES}",
            )
        updates["priority"] = body.priority
    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"status must be one of {_VALID_STATUSES}",
            )
        updates["status"] = body.status
    if body.acceptance_criteria is not None:
        updates["acceptance_criteria"] = body.acceptance_criteria

    if not updates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no fields to update")

    updates["edited_by"] = user["_id"]
    updates["edited_at"] = datetime.now(timezone.utc)

    doc = await db.requirements.find_one_and_update(
        {"_id": oid},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement not found")
    return _to_out(doc)
