from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ..db.mongo import get_db
from ..deps import require_engineer
from ..schemas.conflict import (
    ApplyIn,
    ApplyOut,
    ConflictOut,
    ConflictPatch,
    RequirementRef,
    ResolutionSessionRef,
    ResolutionSuggestion,
)
from ..services.conflict_detector import ConflictDetector
from ..services.conflict_resolution import (
    build_resolution_opener,
    build_resolution_summary,
    build_self_resolution_opener,
)
from ..services.llm_service import LLMService, UpstreamUnavailable
from ..services.resolution_suggester import ResolutionSuggester

router = APIRouter(tags=["conflicts"])

_VALID_CONFLICT_STATUSES = {"resolved", "dismissed"}


def _make_detector() -> ConflictDetector:
    return ConflictDetector(llm=LLMService())


def _make_suggester() -> ResolutionSuggester:
    return ResolutionSuggester(llm=LLMService())


async def _resolution_transcript(db, conflict_id: str) -> list[dict]:
    """Flatten every resolution-chat turn for a conflict into role/content dicts."""
    transcript: list[dict] = []
    async for s in db.sessions.find({"conflict_id": conflict_id, "kind": "conflict_resolution"}):
        async for t in db.turns.find({"session_id": str(s["_id"])}).sort("created_at", 1):
            transcript.append({"role": t["role"], "content": t["content"]})
    return transcript


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


async def _resolution_refs(db, conflict_id: str, session_names: dict) -> list[ResolutionSessionRef]:
    """List the auto-opened resolution chats for a conflict (with stakeholder names)."""
    refs: list[ResolutionSessionRef] = []
    async for s in db.sessions.find({"conflict_id": conflict_id, "kind": "conflict_resolution"}):
        refs.append(
            ResolutionSessionRef(id=str(s["_id"]), stakeholder=session_names.get(str(s["_id"])))
        )
    return refs


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
        resolution_sessions=await _resolution_refs(db, str(doc["_id"]), session_names),
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


async def _create_resolution_session(
    db, *, project_id: str, conflict_id: str, stakeholder_id: str, opener: str, summary: str
) -> None:
    """Idempotently open one conflict-resolution chat plus its AI opening turn."""
    existing = await db.sessions.find_one(
        {"conflict_id": conflict_id, "stakeholder_id": stakeholder_id, "kind": "conflict_resolution"}
    )
    if existing:
        return
    now = datetime.now(timezone.utc)
    try:
        res = await db.sessions.insert_one(
            {
                "project_id": project_id,
                "stakeholder_id": stakeholder_id,
                "title": "Resolve requirement conflict",
                "kind": "conflict_resolution",
                "conflict_id": conflict_id,
                "status": "active",
                "phase": "validation",
                "summary": summary,
                "auto_named": True,
                "created_at": now,
                "updated_at": now,
            }
        )
    except DuplicateKeyError:
        # A unique session index (or a concurrent detect) rejected the insert. Treat as
        # already-open rather than 500-ing the whole detection run.
        return
    await db.turns.insert_one(
        {
            "session_id": str(res.inserted_id),
            "role": "agent",
            "content": opener,
            "created_at": now,
        }
    )


async def _ensure_resolution_sessions(
    db,
    *,
    conflict_id: str,
    project_id: str,
    requirement_a: str,
    requirement_b: str,
    explanation: str,
    session_names: dict,
    project_title: str | None,
) -> None:
    """Open a resolution chat for each distinct stakeholder behind an open conflict.

    Same-stakeholder conflict → one chat; cross-stakeholder → one per side, each
    framed from that stakeholder's point of view. Idempotent per (conflict, stakeholder).
    """
    try:
        req_a = await db.requirements.find_one({"_id": ObjectId(requirement_a)})
        req_b = await db.requirements.find_one({"_id": ObjectId(requirement_b)})
    except Exception:
        return
    if not req_a or not req_b:
        return
    try:
        sess_a = await db.sessions.find_one({"_id": ObjectId(req_a["session_id"])})
        sess_b = await db.sessions.find_one({"_id": ObjectId(req_b["session_id"])})
    except Exception:
        return
    if not sess_a or not sess_b:
        return

    uid_a, uid_b = sess_a["stakeholder_id"], sess_b["stakeholder_id"]
    name_a = session_names.get(req_a["session_id"])
    name_b = session_names.get(req_b["session_id"])
    stmt_a, stmt_b = req_a["statement"], req_b["statement"]

    if uid_a == uid_b:
        await _create_resolution_session(
            db,
            project_id=project_id,
            conflict_id=conflict_id,
            stakeholder_id=uid_a,
            opener=build_self_resolution_opener(
                stakeholder_name=name_a,
                statement_a=stmt_a,
                statement_b=stmt_b,
                explanation=explanation,
                project_title=project_title,
            ),
            summary=build_resolution_summary(
                their_statement=stmt_a,
                other_statement=stmt_b,
                explanation=explanation,
                same_stakeholder=True,
            ),
        )
        return

    await _create_resolution_session(
        db,
        project_id=project_id,
        conflict_id=conflict_id,
        stakeholder_id=uid_a,
        opener=build_resolution_opener(
            stakeholder_name=name_a,
            their_statement=stmt_a,
            other_statement=stmt_b,
            explanation=explanation,
            project_title=project_title,
        ),
        summary=build_resolution_summary(
            their_statement=stmt_a,
            other_statement=stmt_b,
            explanation=explanation,
            same_stakeholder=False,
        ),
    )
    await _create_resolution_session(
        db,
        project_id=project_id,
        conflict_id=conflict_id,
        stakeholder_id=uid_b,
        opener=build_resolution_opener(
            stakeholder_name=name_b,
            their_statement=stmt_b,
            other_statement=stmt_a,
            explanation=explanation,
            project_title=project_title,
        ),
        summary=build_resolution_summary(
            their_statement=stmt_b,
            other_statement=stmt_a,
            explanation=explanation,
            same_stakeholder=False,
        ),
    )


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

    project = await db.projects.find_one({"_id": ObjectId(pid)})
    project_title = (project or {}).get("title")

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
            conflict_id = str(existing["_id"])
            conflict_status = existing.get("status", "open")
        else:
            res = await db.conflicts.insert_one(
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
            conflict_id = str(res.inserted_id)
            conflict_status = "open"

        # Auto-open resolution chats only for live (open) conflicts — never for ones
        # the engineer already resolved/dismissed. Idempotent across re-detection.
        if conflict_status == "open":
            await _ensure_resolution_sessions(
                db,
                conflict_id=conflict_id,
                project_id=pid,
                requirement_a=a,
                requirement_b=b,
                explanation=pair["explanation"],
                session_names=session_names,
                project_title=project_title,
            )

    # Resolution sessions were just created, so refresh the session→name map to
    # label each resolution chat with its stakeholder in the response.
    refreshed = await _project_session_names(db, user["_id"], pid)
    return await _list_conflicts(db, pid, refreshed or session_names, "open")


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


@router.post("/conflicts/{cid}/suggest", response_model=ResolutionSuggestion)
async def suggest_resolution(cid: str, user: dict = Depends(require_engineer)):
    """Draft reconciled wording for a conflict from its resolution chat(s).

    Suggestion only — the RE reviews/edits it and commits via PATCH /requirements.
    """
    db = get_db()
    try:
        oid = ObjectId(cid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found") from exc
    conflict = await db.conflicts.find_one({"_id": oid})
    if not conflict:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")
    # Ownership: returns None unless this engineer owns the conflict's project.
    if await _project_session_names(db, user["_id"], conflict["project_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")

    try:
        req_a = await db.requirements.find_one({"_id": ObjectId(conflict["requirement_a"])})
        req_b = await db.requirements.find_one({"_id": ObjectId(conflict["requirement_b"])})
    except Exception:
        req_a = req_b = None
    if not req_a or not req_b:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict references a removed requirement")

    sess_a = await db.sessions.find_one({"_id": ObjectId(req_a["session_id"])})
    sess_b = await db.sessions.find_one({"_id": ObjectId(req_b["session_id"])})
    same = bool(sess_a and sess_b and sess_a["stakeholder_id"] == sess_b["stakeholder_id"])

    try:
        result = await _make_suggester().suggest(
            statement_a=req_a["statement"],
            statement_b=req_b["statement"],
            explanation=conflict.get("explanation", ""),
            transcript=await _resolution_transcript(db, cid),
            same_stakeholder=same,
        )
    except UpstreamUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return ResolutionSuggestion(**result)


@router.post("/conflicts/{cid}/apply", response_model=ApplyOut)
async def apply_resolution(cid: str, body: ApplyIn, user: dict = Depends(require_engineer)):
    """Commit the reconciled wording: write it to the surviving requirement, reject
    the counterpart, and resolve the conflict — atomically, in one RE action."""
    db = get_db()
    try:
        oid = ObjectId(cid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found") from exc
    conflict = await db.conflicts.find_one({"_id": oid})
    if not conflict:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")
    if await _project_session_names(db, user["_id"], conflict["project_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")

    surviving = body.surviving_requirement_id
    pair = {conflict["requirement_a"], conflict["requirement_b"]}
    if surviving not in pair:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "surviving_requirement_id must be one of the conflict's requirements",
        )
    counterpart = (pair - {surviving}).pop()

    statement = (body.statement or "").strip()
    if not statement:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "statement is required")

    try:
        surv_doc = await db.requirements.find_one({"_id": ObjectId(surviving)})
        ctr_doc = await db.requirements.find_one({"_id": ObjectId(counterpart)})
    except Exception:
        surv_doc = ctr_doc = None
    if not surv_doc or not ctr_doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict references a removed requirement")

    now = datetime.now(timezone.utc)
    await db.requirements.update_one(
        {"_id": ObjectId(surviving)},
        {"$set": {"statement": statement, "edited_by": user["_id"], "edited_at": now}},
    )
    await db.requirements.update_one(
        {"_id": ObjectId(counterpart)},
        {"$set": {"status": "rejected", "edited_by": user["_id"], "edited_at": now}},
    )
    await db.conflicts.update_one(
        {"_id": oid},
        {"$set": {"status": "resolved", "resolved_by": user["_id"], "updated_at": now}},
    )
    return ApplyOut(id=cid, status="resolved")
