from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import settings
from ..db.mongo import get_db
from ..deps import current_user_id_from_token, require_stakeholder
from ..schemas.dialogue import TurnIn, QuestionOut, TurnOut, TurnResponse, MessageResponse
from ..services.question_generator import QuestionGenerator
from ..services.llm_service import LLMService, UpstreamUnavailable
from ..services.requirement_extractor import RequirementExtractor
from ..services.title_generator import TitleGenerator
from ..services.resolution_tracker import ResolutionTracker
from ..schemas.conflict import ResolutionStanceOut

router = APIRouter(prefix="/sessions", tags=["dialogue"])


def _make_generator() -> QuestionGenerator:
    # Probing questions use the lighter/faster model to cut per-turn latency,
    # with the standard model as fallback if the light one is unavailable.
    return QuestionGenerator(
        llm=LLMService(
            model=settings.gemini_question_model,
            fallback_model=settings.gemini_model,
        )
    )


def _make_extractor() -> RequirementExtractor:
    return RequirementExtractor(llm=LLMService())


def _make_title_generator() -> TitleGenerator:
    return TitleGenerator(llm=LLMService())


def _make_resolution_tracker() -> ResolutionTracker:
    return ResolutionTracker(llm=LLMService())


async def _maybe_auto_name(db, session: dict, oid, stakeholder_text: str) -> str:
    """If the session is still unnamed, derive a title from the first message.

    Returns the resolved title (new or existing). Best-effort: any failure leaves
    the placeholder in place and never blocks the reply.
    """
    current = session.get("title")
    if session.get("auto_named"):
        return current
    try:
        title = await _make_title_generator().generate(stakeholder_text)
        await db.sessions.update_one(
            {"_id": oid},
            {"$set": {"title": title, "auto_named": True, "updated_at": datetime.now(timezone.utc)}},
        )
        return title
    except Exception:
        return current


async def _build_summary(db, session: dict) -> str:
    """Build the AI context string: project background prepended to session summary."""
    project = await db.projects.find_one({"_id": ObjectId(session["project_id"])})
    project_context = (project or {}).get("background") or ""
    base_summary = session.get("summary") or ""
    return (project_context + "\n\n" + base_summary).strip() if project_context else base_summary


import re

_REQ_STOPWORDS = {
    "the", "a", "an",
    "shall", "will", "can", "may", "should", "must", "could", "would",
    "is", "are", "be", "been", "being",
    "able", "to",
    "user", "users", "system",
}
_DEDUP_THRESHOLD = 0.55


def _tokenize_statement(s: str) -> set[str]:
    """Lowercase + alphanumeric tokens, with requirement boilerplate (shall/system/etc.) removed."""
    words = re.findall(r"[a-z0-9]+", s.lower())
    return {w for w in words if w not in _REQ_STOPWORDS and len(w) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Consecutive stakeholder turns with no NEW requirement before the agent suggests
# wrapping up. The dedup result (an empty doc list) is the saturation signal.
_SATURATION_THRESHOLD = 3


# Phrases that explicitly signal the stakeholder is finished. Matched cheaply (no
# LLM) so the wrap-up prompt can surface immediately on an "I'm done" instead of
# waiting for the saturation streak to build up over several no-new-info turns.
_DONE_INTENT = re.compile(
    r"\b(i['’]?m done|i am done|we['’]?re done|we are done|"
    r"that['’]?s all|that is all|that['’]?s everything|that is everything|"
    r"that['’]?s it|that is it|nothing else|nothing further|nothing more|"
    r"no more (?:questions|to add)|we['’]?ve covered everything|"
    r"covered everything|that covers it|i think that covers|all good)\b",
    re.IGNORECASE,
)


def _looks_done(content: str) -> bool:
    """True when the stakeholder message reads as an explicit 'I'm finished' signal."""
    return bool(_DONE_INTENT.search(content or ""))


async def _dedup_requirement_docs(db, sid: str, stakeholder_turn_id: str, extracted: list[dict], now) -> list[dict]:
    """Return only the requirement docs that aren't a near-duplicate of an existing
    requirement OF THE SAME TYPE.

    Dedup is scoped per type on purpose: a non-functional threshold and the
    functional behaviour it qualifies often share most of their words
    (e.g. "register a QR check-in" vs "register a QR check-in within 5 seconds")
    yet are distinct requirements — comparing across types would wrongly drop the NFR.
    """
    existing_by_type: dict[str, list[set[str]]] = {}
    async for r in db.requirements.find({"session_id": sid}, {"statement": 1, "type": 1}):
        existing_by_type.setdefault(r.get("type"), []).append(_tokenize_statement(r["statement"]))

    docs: list[dict] = []
    for r in extracted:
        statement = r.get("statement")
        rtype = r.get("type")
        if not statement or not rtype:
            continue
        new_tokens = _tokenize_statement(statement)
        bucket = existing_by_type.setdefault(rtype, [])
        if any(_jaccard(new_tokens, e) >= _DEDUP_THRESHOLD for e in bucket):
            continue
        bucket.append(new_tokens)
        docs.append({
            "session_id": sid,
            "statement": statement,
            "type": rtype,
            "source_turn_id": stakeholder_turn_id,
            "created_at": now,
        })
    return docs


async def _extract_and_track_saturation(
    db, session: dict, sid: str, stakeholder_turn_id: str, content: str, now
) -> bool:
    """Extract+dedup+store requirements for an interview turn, and track saturation.

    Returns whether the agent should suggest wrapping up. Conflict-resolution chats
    clarify rather than mint spec rows, so they skip extraction and never wrap up.
    A turn that adds a new requirement resets the streak; an empty turn advances it,
    and once the streak hits the threshold the wrap-up suggestion latches on.
    """
    if session.get("kind") == "conflict_resolution":
        return False

    extractor = _make_extractor()
    try:
        extracted = await extractor.extract(content)
    except Exception:
        extracted = []
    docs = (
        await _dedup_requirement_docs(db, sid, stakeholder_turn_id, extracted, now)
        if extracted
        else []
    )

    # An explicit "I'm done"-style message offers to wrap up right away, regardless
    # of whether this turn added a requirement or where the saturation streak stands.
    done = _looks_done(content)

    if docs:
        await db.requirements.insert_many(docs)
        await db.sessions.update_one(
            {"_id": session["_id"]},
            {"$set": {"saturation_streak": 0, "wrap_up_suggested": done}},
        )
        return done

    streak = session.get("saturation_streak", 0) + 1
    suggest = done or streak >= _SATURATION_THRESHOLD
    await db.sessions.update_one(
        {"_id": session["_id"]},
        {"$set": {
            # On an explicit done-signal, latch the streak at the threshold so the
            # suggestion sticks across following turns until real input resets it.
            "saturation_streak": max(streak, _SATURATION_THRESHOLD) if done else streak,
            "wrap_up_suggested": suggest,
        }},
    )
    return suggest


async def _track_resolution(db, session: dict, sid: str, now) -> dict | None:
    """For a conflict-resolution turn: detect a reached resolution and, if so, write
    the stance onto the conflict and pause probing. Returns the API stance dict (or
    None). Bails safely — without constructing the LLM — when the conflict or its
    requirements can't be loaded, so a malformed conflict_id never 500s a reply.
    """
    conflict_id = session.get("conflict_id")
    if not conflict_id:
        return None
    try:
        conflict = await db.conflicts.find_one({"_id": ObjectId(conflict_id)})
    except Exception:
        conflict = None
    if not conflict:
        return None
    try:
        req_a = await db.requirements.find_one({"_id": ObjectId(conflict["requirement_a"])})
        req_b = await db.requirements.find_one({"_id": ObjectId(conflict["requirement_b"])})
    except Exception:
        req_a = req_b = None
    if not req_a or not req_b:
        return None

    try:
        sess_a = await db.sessions.find_one({"_id": ObjectId(req_a["session_id"])})
        sess_b = await db.sessions.find_one({"_id": ObjectId(req_b["session_id"])})
    except Exception:
        sess_a = sess_b = None
    same = bool(sess_a and sess_b and sess_a.get("stakeholder_id") == sess_b.get("stakeholder_id"))

    transcript = [
        {"role": t["role"], "content": t["content"]}
        async for t in db.turns.find({"session_id": sid}).sort("created_at", 1)
    ]
    try:
        result = await _make_resolution_tracker().track(
            statement_a=req_a["statement"],
            statement_b=req_b["statement"],
            explanation=conflict.get("explanation", ""),
            transcript=transcript,
            same_stakeholder=same,
        )
    except Exception:
        return None
    if not result.get("reached"):
        return None

    await db.conflicts.update_one(
        {"_id": conflict["_id"]},
        {"$set": {
            f"resolutions.{session['stakeholder_id']}": {
                "decision": result["decision"],
                "statement": result.get("statement"),
                "session_id": sid,
                "captured_at": now,
            },
            "updated_at": now,
        }},
    )
    await db.sessions.update_one(
        {"_id": session["_id"]},
        {"$set": {"wrap_up_suggested": True, "updated_at": now}},
    )
    return {
        "stakeholder": None,
        "decision": result["decision"],
        "statement": result.get("statement"),
        "captured_at": now,
    }


async def _process_stakeholder_turn(
    db, session: dict, sid: str, stakeholder_turn_id: str, content: str, now
) -> tuple[bool, dict | None]:
    """Interview turns extract requirements + track saturation; conflict turns track
    resolution. Returns (wrap_up_suggested, resolution-stance-or-None)."""
    if session.get("kind") == "conflict_resolution":
        stance = await _track_resolution(db, session, sid, now)
        return (stance is not None, stance)
    wrap = await _extract_and_track_saturation(db, session, sid, stakeholder_turn_id, content, now)
    return (wrap, None)


@router.post("/{sid}/turns", response_model=TurnResponse)
async def post_turn(
    sid: str,
    body: TurnIn,
    count: int = Query(default=5, ge=1, le=10),
    user: dict = Depends(require_stakeholder),
):
    user_id = user["_id"]
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc

    session = await db.sessions.find_one({"_id": oid, "stakeholder_id": user_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    if session["status"] == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "session has ended")

    summary = await _build_summary(db, session)

    now = datetime.now(timezone.utc)
    stakeholder_doc = {
        "session_id": sid,
        "role": "stakeholder",
        "content": body.content,
        "created_at": now,
    }
    res = await db.turns.insert_one(stakeholder_doc)
    stakeholder_turn_id = str(res.inserted_id)

    await _maybe_auto_name(db, session, oid, body.content)

    wrap_up_suggested, resolution = await _process_stakeholder_turn(
        db, session, sid, stakeholder_turn_id, body.content, now
    )

    history: list[dict] = []
    async for t in db.turns.find({"session_id": sid}).sort("created_at", 1):
        history.append(
            {
                "role": t["role"],
                "content": t["content"],
                "strategy": t.get("strategy"),
            }
        )

    gen = _make_generator()
    phase = session["phase"]

    questions_out: list[QuestionOut] = []
    for _ in range(count):
        q = await gen.next_question(
            phase=phase, summary=summary, history=history, kind=session.get("kind", "interview")
        )
        agent_doc = {
            "session_id": sid,
            "role": "agent",
            "content": q.question,
            "strategy": q.strategy,
            "validator_attempts": q.attempts,
            "validator_verdict": "valid" if q.valid else "invalid",
            "created_at": datetime.now(timezone.utc),
        }
        agent_res = await db.turns.insert_one(agent_doc)
        questions_out.append(
            QuestionOut(id=str(agent_res.inserted_id), content=q.question, strategy=q.strategy)
        )
        history.append({"role": "agent", "content": q.question, "strategy": q.strategy})

    return TurnResponse(
        stakeholder_turn_id=stakeholder_turn_id,
        questions=questions_out,
        wrap_up_suggested=wrap_up_suggested,
        resolution=ResolutionStanceOut(**resolution) if resolution else None,
    )


@router.post("/{sid}/messages", response_model=MessageResponse)
async def post_message(
    sid: str,
    body: TurnIn,
    user: dict = Depends(require_stakeholder),
):
    user_id = user["_id"]
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    session = await db.sessions.find_one({"_id": oid, "stakeholder_id": user_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    if session["status"] == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "session has ended")

    now = datetime.now(timezone.utc)
    stakeholder_doc = {
        "session_id": sid,
        "role": "stakeholder",
        "content": body.content,
        "created_at": now,
    }
    res = await db.turns.insert_one(stakeholder_doc)
    stakeholder_turn_id = str(res.inserted_id)

    session_title = await _maybe_auto_name(db, session, oid, body.content)

    wrap_up_suggested, resolution = await _process_stakeholder_turn(
        db, session, sid, stakeholder_turn_id, body.content, now
    )

    return MessageResponse(
        stakeholder_turn_id=stakeholder_turn_id,
        session_title=session_title,
        wrap_up_suggested=wrap_up_suggested,
        resolution=ResolutionStanceOut(**resolution) if resolution else None,
    )


@router.post("/{sid}/questions", response_model=QuestionOut)
async def post_question(
    sid: str,
    user: dict = Depends(require_stakeholder),
):
    user_id = user["_id"]
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    session = await db.sessions.find_one({"_id": oid, "stakeholder_id": user_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    if session["status"] == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "session has ended")

    summary = await _build_summary(db, session)

    history: list[dict] = []
    async for t in db.turns.find({"session_id": sid}).sort("created_at", 1):
        history.append({
            "role": t["role"],
            "content": t["content"],
            "strategy": t.get("strategy"),
        })

    gen = _make_generator()
    try:
        q = await gen.next_question(
            phase=session["phase"],
            summary=summary,
            history=history,
            kind=session.get("kind", "interview"),
        )
    except UpstreamUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    agent_doc = {
        "session_id": sid,
        "role": "agent",
        "content": q.question,
        "strategy": q.strategy,
        "validator_attempts": q.attempts,
        "validator_verdict": "valid" if q.valid else "invalid",
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.turns.insert_one(agent_doc)
    return QuestionOut(id=str(res.inserted_id), content=q.question, strategy=q.strategy)


@router.get("/{sid}/turns", response_model=list[TurnOut])
async def list_turns(
    sid: str,
    user_id: str = Depends(current_user_id_from_token),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc

    session = await db.sessions.find_one({"_id": oid})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    if session.get("stakeholder_id") != user_id:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        is_re = user and user.get("role") == "requirements_engineer"
        owns_project = is_re and await db.projects.find_one(
            {"_id": ObjectId(session["project_id"]), "owner_id": user_id}
        )
        if not owns_project:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    out: list[TurnOut] = []
    async for t in db.turns.find({"session_id": sid}).sort("created_at", 1):
        out.append(
            TurnOut(
                id=str(t["_id"]),
                role=t["role"],
                content=t["content"],
                strategy=t.get("strategy"),
                created_at=t["created_at"],
            )
        )
    return out
