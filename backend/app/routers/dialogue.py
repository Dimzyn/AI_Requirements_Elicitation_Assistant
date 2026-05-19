from bson import ObjectId
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db.mongo import get_db
from ..deps import current_user_id_from_token
from ..schemas.dialogue import TurnIn, QuestionOut, TurnOut, TurnResponse
from ..services.question_generator import QuestionGenerator
from ..services.llm_service import LLMService
from ..services.requirement_extractor import RequirementExtractor

router = APIRouter(prefix="/sessions", tags=["dialogue"])


def _make_generator() -> QuestionGenerator:
    return QuestionGenerator(llm=LLMService())


def _make_extractor() -> RequirementExtractor:
    return RequirementExtractor(llm=LLMService())


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
        docs = [
            {
                "session_id": sid,
                "statement": r["statement"],
                "type": r["type"],
                "source_turn_id": stakeholder_turn_id,
                "created_at": now,
            }
            for r in extracted
            if r.get("statement") and r.get("type")
        ]
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

    session = await db.sessions.find_one({"_id": oid, "user_id": user_id})
    if not session:
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
