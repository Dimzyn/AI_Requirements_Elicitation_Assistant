from bson import ObjectId
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db.mongo import get_db
from ..deps import current_user_id_from_token
from ..schemas.dialogue import TurnIn, QuestionOut, TurnOut, TurnResponse, MessageResponse
from ..services.question_generator import QuestionGenerator
from ..services.llm_service import LLMService, UpstreamUnavailable
from ..services.requirement_extractor import RequirementExtractor

router = APIRouter(prefix="/sessions", tags=["dialogue"])


def _make_generator() -> QuestionGenerator:
    return QuestionGenerator(llm=LLMService())


def _make_extractor() -> RequirementExtractor:
    return RequirementExtractor(llm=LLMService())


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


async def _dedup_requirement_docs(db, sid: str, stakeholder_turn_id: str, extracted: list[dict], now) -> list[dict]:
    """Return only the requirement docs whose token-set isn't a near-duplicate of an existing one."""
    existing_tokens: list[set[str]] = []
    async for r in db.requirements.find({"session_id": sid}, {"statement": 1}):
        existing_tokens.append(_tokenize_statement(r["statement"]))

    docs: list[dict] = []
    for r in extracted:
        statement = r.get("statement")
        rtype = r.get("type")
        if not statement or not rtype:
            continue
        new_tokens = _tokenize_statement(statement)
        if any(_jaccard(new_tokens, e) >= _DEDUP_THRESHOLD for e in existing_tokens):
            continue
        existing_tokens.append(new_tokens)
        docs.append({
            "session_id": sid,
            "statement": statement,
            "type": rtype,
            "source_turn_id": stakeholder_turn_id,
            "created_at": now,
        })
    return docs


@router.post("/{sid}/turns", response_model=TurnResponse)
async def post_turn(
    sid: str,
    body: TurnIn,
    count: int = Query(default=5, ge=1, le=10),
    user_id: str = Depends(current_user_id_from_token),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc

    session = await db.sessions.find_one({"_id": oid, "user_id": user_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    now = datetime.utcnow()
    stakeholder_doc = {
        "session_id": sid,
        "role": "stakeholder",
        "content": body.content,
        "created_at": now,
    }
    res = await db.turns.insert_one(stakeholder_doc)
    stakeholder_turn_id = str(res.inserted_id)

    extractor = _make_extractor()
    try:
        extracted = await extractor.extract(body.content)
    except Exception:
        extracted = []
    if extracted:
        docs = await _dedup_requirement_docs(db, sid, stakeholder_turn_id, extracted, now)
        if docs:
            await db.requirements.insert_many(docs)

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
    summary = session.get("summary") or ""

    questions_out: list[QuestionOut] = []
    for _ in range(count):
        q = await gen.next_question(phase=phase, summary=summary, history=history)
        agent_doc = {
            "session_id": sid,
            "role": "agent",
            "content": q.question,
            "strategy": q.strategy,
            "validator_attempts": q.attempts,
            "validator_verdict": "valid" if q.valid else "invalid",
            "created_at": datetime.utcnow(),
        }
        agent_res = await db.turns.insert_one(agent_doc)
        questions_out.append(
            QuestionOut(id=str(agent_res.inserted_id), content=q.question, strategy=q.strategy)
        )
        history.append({"role": "agent", "content": q.question, "strategy": q.strategy})

    return TurnResponse(stakeholder_turn_id=stakeholder_turn_id, questions=questions_out)


@router.post("/{sid}/messages", response_model=MessageResponse)
async def post_message(
    sid: str,
    body: TurnIn,
    user_id: str = Depends(current_user_id_from_token),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    session = await db.sessions.find_one({"_id": oid, "user_id": user_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    now = datetime.utcnow()
    stakeholder_doc = {
        "session_id": sid,
        "role": "stakeholder",
        "content": body.content,
        "created_at": now,
    }
    res = await db.turns.insert_one(stakeholder_doc)
    stakeholder_turn_id = str(res.inserted_id)

    extractor = _make_extractor()
    try:
        extracted = await extractor.extract(body.content)
    except Exception:
        extracted = []
    if extracted:
        docs = await _dedup_requirement_docs(db, sid, stakeholder_turn_id, extracted, now)
        if docs:
            await db.requirements.insert_many(docs)

    return MessageResponse(stakeholder_turn_id=stakeholder_turn_id)


@router.post("/{sid}/questions", response_model=QuestionOut)
async def post_question(
    sid: str,
    user_id: str = Depends(current_user_id_from_token),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    session = await db.sessions.find_one({"_id": oid, "user_id": user_id})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

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
            summary=session.get("summary") or "",
            history=history,
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
        "created_at": datetime.utcnow(),
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
    if session.get("user_id") != user_id:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        if not user or user.get("role") != "requirements_engineer":
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
