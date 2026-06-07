from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from ..db.mongo import get_db
from ..deps import require_engineer
from ..schemas.conflict import ConflictOut, ConflictPatch, RequirementRef
from ..services.conflict_detector import ConflictDetector
from ..services.llm_service import LLMService, UpstreamUnavailable

router = APIRouter(tags=["conflicts"])

_VALID_CONFLICT_STATUSES = {"resolved", "dismissed"}


def _make_detector() -> ConflictDetector:
    return ConflictDetector(llm=LLMService())


async def _project_session_names(db, owner_id: str, project_id: str) -> dict | None:
    """Return {session_id: stakeholder_name|None} for an owned project, else None.

    None signals the project does not exist or is not owned by this engineer.
    """
    try:
        oid = ObjectId(project_id)
    except Exception:
        return None
    project = await db.projects.find_one({"_id": oid, "owner_id": owner_id})
    if not project:
        return None

    session_to_uid: dict[str, str | None] = {}
    async for s in db.sessions.find({"project_id": project_id}):
        session_to_uid[str(s["_id"])] = s.get("stakeholder_id")

    uid_to_name: dict[str, str | None] = {}
    for uid in {u for u in session_to_uid.values() if u}:
        try:
            user = await db.users.find_one({"_id": ObjectId(uid)})
        except Exception:
            user = None
        uid_to_name[uid] = (user or {}).get("real_name")

    return {sid: uid_to_name.get(uid) for sid, uid in session_to_uid.items()}


async def _req_ref(db, rid: str, session_names: dict) -> RequirementRef | None:
    """Build a RequirementRef for a live, non-rejected requirement, else None (stale)."""
    try:
        oid = ObjectId(rid)
    except Exception:
        return None
    r = await db.requirements.find_one({"_id": oid})
    if not r or r.get("status") == "rejected":
        return None
    return RequirementRef(
        id=rid,
        statement=r["statement"],
        stakeholder=session_names.get(r["session_id"]),
    )


async def _conflict_to_out(db, doc: dict, session_names: dict) -> ConflictOut | None:
    """Enrich a stored conflict; returns None when either requirement is gone/rejected."""
    ref_a = await _req_ref(db, doc["requirement_a"], session_names)
    ref_b = await _req_ref(db, doc["requirement_b"], session_names)
    if ref_a is None or ref_b is None:
        return None
    return ConflictOut(
        id=str(doc["_id"]),
        project_id=doc["project_id"],
        status=doc.get("status", "open"),
        explanation=doc.get("explanation", ""),
        requirement_a=ref_a,
        requirement_b=ref_b,
        detected_at=doc["detected_at"],
    )


async def _list_conflicts(db, project_id: str, session_names: dict, status_filter: str | None) -> list[ConflictOut]:
    query: dict = {"project_id": project_id}
    if status_filter:
        query["status"] = status_filter
    out: list[ConflictOut] = []
    async for doc in db.conflicts.find(query).sort("detected_at", 1):
        enriched = await _conflict_to_out(db, doc, session_names)
        if enriched is not None:
            out.append(enriched)
    return out


@router.post("/projects/{pid}/conflicts/detect", response_model=list[ConflictOut])
async def detect_conflicts(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    session_names = await _project_session_names(db, user["_id"], pid)
    if session_names is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")

    sids = list(session_names.keys())
    requirements: list[dict] = []
    if sids:
        async for r in db.requirements.find(
            {"session_id": {"$in": sids}, "status": {"$ne": "rejected"}}
        ):
            requirements.append(
                {
                    "id": str(r["_id"]),
                    "statement": r["statement"],
                    "type": r.get("type"),
                    "stakeholder": session_names.get(r["session_id"]),
                }
            )

    detector = _make_detector()
    try:
        found = await detector.detect(requirements)
    except UpstreamUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    now = datetime.now(timezone.utc)
    for pair in found:
        a = pair["requirement_a"]
        b = pair["requirement_b"]
        pair_key = f"{a}:{b}"  # ids already sorted by the detector
        existing = await db.conflicts.find_one({"project_id": pid, "pair_key": pair_key})
        if existing:
            await db.conflicts.update_one(
                {"_id": existing["_id"]},
                {"$set": {"explanation": pair["explanation"], "updated_at": now}},
            )
        else:
            await db.conflicts.insert_one(
                {
                    "project_id": pid,
                    "requirement_a": a,
                    "requirement_b": b,
                    "pair_key": pair_key,
                    "explanation": pair["explanation"],
                    "status": "open",
                    "detected_at": now,
                    "updated_at": now,
                    "resolved_by": None,
                }
            )

    return await _list_conflicts(db, pid, session_names, "open")


@router.get("/projects/{pid}/conflicts", response_model=list[ConflictOut])
async def list_conflicts(
    pid: str,
    conflict_status: str | None = Query(default=None, alias="status"),
    user: dict = Depends(require_engineer),
):
    db = get_db()
    session_names = await _project_session_names(db, user["_id"], pid)
    if session_names is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return await _list_conflicts(db, pid, session_names, conflict_status)


@router.patch("/conflicts/{cid}", response_model=ConflictOut)
async def patch_conflict(cid: str, body: ConflictPatch, user: dict = Depends(require_engineer)):
    db = get_db()
    try:
        oid = ObjectId(cid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found") from exc

    conflict = await db.conflicts.find_one({"_id": oid})
    if not conflict:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")

    session_names = await _project_session_names(db, user["_id"], conflict["project_id"])
    if session_names is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")

    if body.status not in _VALID_CONFLICT_STATUSES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"status must be one of {_VALID_CONFLICT_STATUSES}",
        )

    now = datetime.now(timezone.utc)
    doc = await db.conflicts.find_one_and_update(
        {"_id": oid},
        {"$set": {"status": body.status, "resolved_by": user["_id"], "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    out = await _conflict_to_out(db, doc, session_names)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict references a removed requirement")
    return out
