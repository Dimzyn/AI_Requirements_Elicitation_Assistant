# Conflict Probing Rule + Resolution Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give conflict-resolution sessions a goal-directed probing rule set that drives to resolve requirements A vs B, and capture the stakeholder's converged resolution as a stance surfaced to the stakeholder and the RE.

**Architecture:** The existing `QuestionGenerator` branches on `session.kind`: interview sessions keep the round-robin `StrategySelector`; conflict sessions use a new deterministic `ConflictStrategySelector`. Each stakeholder turn in a conflict session runs a new `ResolutionTracker` (LLM, JSON-mode) that detects a reached resolution and writes a per-stakeholder stance onto the conflict document, reusing the existing `wrap_up_suggested` mechanism to pause probing. The stance is exposed through `ConflictOut`, the stakeholder resolution card, and a new RE-side panel.

**Tech Stack:** FastAPI + Motor/MongoDB (backend, pytest + mongomock-motor), React 19 + Zustand + Vite (frontend, vitest), Google Gemini via `LLMService`.

## Global Constraints

- Backend targets Python 3.11; run backend tests from `backend/` (`cd backend && python -m pytest ...`); `asyncio_mode = "auto"` so no `@pytest.mark.asyncio` needed on new async tests but existing files use it — match the file you edit.
- Run frontend tests from `frontend/` (`cd frontend && npx vitest run <path>`); typecheck with `npx tsc -b`.
- Question generation stays a SINGLE LLM round-trip (the 14-mistake guard is inline); do not add a validator round-trip.
- Conflict strategy prompts are **perspective-neutral** ("the first/second conflicting requirement", "the other need") — never "your requirement" — because in a cross-stakeholder conflict the second requirement belongs to the other stakeholder.
- `decision` is one of exactly `"a_wins" | "b_wins" | "compromise" | "restate"` and is **relative to the conflict's canonical `requirement_a` / `requirement_b`** (conflict-doc order), so both stakeholders' stances are comparable.
- Reuse the existing `wrap_up_suggested` field/flow to pause probing on a reached resolution; do NOT add a parallel session field.
- Resolution-only: conflict sessions must NEVER mint spec requirement rows (`db.requirements`).
- LLM calls are best-effort: swallow any tracker exception and treat as "not reached" (mirrors `RequirementExtractor`).
- LLM stub for unit tests exposes `async def generate(self, prompt, *, temperature, response_mime_type=None, model=None)`.

---

### Task 1: Conflict strategy prompts + `ConflictStrategySelector`

**Files:**
- Modify: `backend/app/prompts/strategy_prompts.json`
- Modify: `backend/app/services/strategy_selector.py`
- Test: `backend/tests/test_conflict_strategy_selector.py`

**Interfaces:**
- Produces: `ConflictStrategySelector.choose(*, agent_history: list[str]) -> str` returning one of `clarify_intent_a`, `clarify_intent_b`, `weigh_priority`, `explore_middle_ground`, `confirm_resolution`. Also produces those five keys in `strategy_prompts.json`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_conflict_strategy_selector.py`:

```python
import json
from pathlib import Path

from app.services.strategy_selector import ConflictStrategySelector

_PROMPTS = json.loads(
    (Path("app") / "prompts" / "strategy_prompts.json").read_text(encoding="utf-8")
)


def test_first_probe_clarifies_first_requirement():
    assert ConflictStrategySelector().choose(agent_history=[]) == "clarify_intent_a"


def test_progression_advances_by_prior_conflict_turns():
    sel = ConflictStrategySelector()
    assert sel.choose(agent_history=["clarify_intent_a"]) == "clarify_intent_b"
    assert sel.choose(agent_history=["clarify_intent_a", "clarify_intent_b"]) == "weigh_priority"
    assert sel.choose(
        agent_history=["clarify_intent_a", "clarify_intent_b", "weigh_priority"]
    ) == "explore_middle_ground"
    assert sel.choose(
        agent_history=["clarify_intent_a", "clarify_intent_b", "weigh_priority", "explore_middle_ground"]
    ) == "confirm_resolution"


def test_holds_on_confirm_after_progression_exhausted():
    sel = ConflictStrategySelector()
    assert sel.choose(agent_history=["a", "b", "c", "d", "e"]) == "confirm_resolution"
    assert sel.choose(agent_history=["a", "b", "c", "d", "e", "f", "g"]) == "confirm_resolution"


def test_all_five_conflict_prompts_exist():
    for key in (
        "clarify_intent_a",
        "clarify_intent_b",
        "weigh_priority",
        "explore_middle_ground",
        "confirm_resolution",
    ):
        assert key in _PROMPTS and _PROMPTS[key].strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_conflict_strategy_selector.py -v`
Expected: FAIL — `ImportError: cannot import name 'ConflictStrategySelector'`.

- [ ] **Step 3: Add the five conflict strategy prompts**

In `backend/app/prompts/strategy_prompts.json`, add these keys (keep existing keys; valid JSON, comma after the previous last entry):

```json
  "clarify_intent_a": "Ask why the FIRST conflicting requirement matters to the stakeholder — what breaks or is lost without it. Reference that requirement specifically. Do not bring up the other requirement yet.",
  "clarify_intent_b": "Ask about the need behind the SECOND conflicting requirement — why it is important, or who depends on it. Reference that requirement specifically.",
  "weigh_priority": "Ask which of the two conflicting needs matters more in practice, or under what specific conditions each should take precedence (a context or scope split).",
  "explore_middle_ground": "Propose or invite ONE concrete middle ground that could satisfy both conflicting requirements — for example scoping by context, a threshold, or a phased rollout. Keep it specific, not open-ended.",
  "confirm_resolution": "Restate the resolution that is emerging as ONE concrete option (one requirement wins, a compromise, or a reworded requirement) and ask the stakeholder to confirm it is correct."
```

- [ ] **Step 4: Implement `ConflictStrategySelector`**

Append to `backend/app/services/strategy_selector.py`:

```python
class ConflictStrategySelector:
    """Deterministic probing progression for conflict-resolution sessions.

    Unlike the interview StrategySelector, this never pivots to unrelated topics:
    every step drives toward reconciling the two conflicting requirements. The
    index is the number of prior conflict-strategy agent turns (the opener has no
    strategy, so it is excluded by the caller).
    """

    PROGRESSION = [
        "clarify_intent_a",
        "clarify_intent_b",
        "weigh_priority",
        "explore_middle_ground",
        "confirm_resolution",
    ]

    def choose(self, *, agent_history: list[str]) -> str:
        idx = len(agent_history)
        if idx >= len(self.PROGRESSION):
            return self.PROGRESSION[-1]
        return self.PROGRESSION[idx]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_conflict_strategy_selector.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/prompts/strategy_prompts.json backend/app/services/strategy_selector.py backend/tests/test_conflict_strategy_selector.py
git commit -m "feat: conflict-resolution probing strategy set + selector"
```

---

### Task 2: `QuestionGenerator` branches on session kind

**Files:**
- Modify: `backend/app/services/question_generator.py`
- Test: `backend/tests/test_question_generator.py:1-85` (add tests)

**Interfaces:**
- Consumes: `ConflictStrategySelector` from Task 1.
- Produces: `QuestionGenerator.next_question(*, phase, summary, history, kind="interview") -> GeneratedQuestion`. When `kind == "conflict_resolution"`, `strategy` is drawn from `ConflictStrategySelector`; otherwise unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_question_generator.py`:

```python
CONFLICT_HISTORY_START = [
    {"role": "agent", "content": "Here are two clashing requirements — how should we resolve them?"},
    {"role": "stakeholder", "content": "Well, both are important to me for different reasons."},
]


@pytest.mark.asyncio
async def test_conflict_kind_first_probe_clarifies_first_requirement():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(
        phase="validation", summary="conflict ctx", history=CONFLICT_HISTORY_START, kind="conflict_resolution"
    )
    assert result.strategy == "clarify_intent_a"
    # the conflict directive (not an interview one) is embedded in the single prompt
    assert "FIRST conflicting requirement" in llm.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_conflict_kind_progression_advances_with_prior_conflict_turns():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    history = CONFLICT_HISTORY_START + [
        {"role": "agent", "content": "Q1?", "strategy": "clarify_intent_a"},
        {"role": "stakeholder", "content": "Because it saves the team a lot of manual effort."},
    ]
    result = await g.next_question(
        phase="validation", summary="conflict ctx", history=history, kind="conflict_resolution"
    )
    assert result.strategy == "clarify_intent_b"


@pytest.mark.asyncio
async def test_interview_kind_unchanged_default():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert result.strategy == "concept"  # default kind stays interview
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_question_generator.py -k conflict -v`
Expected: FAIL — `next_question() got an unexpected keyword argument 'kind'`.

- [ ] **Step 3: Implement the kind branch**

In `backend/app/services/question_generator.py`, update the import, `__init__`, and `next_question`:

```python
from .strategy_selector import StrategySelector, ConflictStrategySelector
```

```python
    def __init__(
        self,
        *,
        llm,
        ctx: Optional[ContextManager] = None,
        sel: Optional[StrategySelector] = None,
        conflict_sel: Optional[ConflictStrategySelector] = None,
    ) -> None:
        self.llm = llm
        self.ctx = ctx or ContextManager()
        self.sel = sel or StrategySelector()
        self.conflict_sel = conflict_sel or ConflictStrategySelector()

    async def next_question(
        self, *, phase: str, summary: str, history: list, kind: str = "interview"
    ) -> GeneratedQuestion:
        agent_history = [t.get("strategy") for t in history if t["role"] == "agent" and t.get("strategy")]
        last_stakeholder = next(
            (t["content"] for t in reversed(history) if t["role"] == "stakeholder"), ""
        )
        if kind == "conflict_resolution":
            strategy = self.conflict_sel.choose(agent_history=agent_history)
        else:
            strategy = self.sel.choose(agent_history=agent_history, last_stakeholder=last_stakeholder)

        context_prompt = self.ctx.build_prompt(phase=phase, summary=summary, history=history)
        prompt = (
            f"{context_prompt}\n\n"
            f"Strategy directive: {_STRATS[strategy]}\n\n"
            f"{_MISTAKE_GUARD}"
        )

        raw = await self.llm.generate(prompt, temperature=0.7, response_mime_type="application/json")
        question = (json.loads(raw).get("draft_question") or "").strip()
        return GeneratedQuestion(
            question=question,
            strategy=strategy,
            attempts=1,
            valid=True,
            mistakes=[],
        )
```

- [ ] **Step 4: Run the full generator suite to verify pass + no regressions**

Run: `cd backend && python -m pytest tests/test_question_generator.py -v`
Expected: PASS (all existing + 3 new tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/question_generator.py backend/tests/test_question_generator.py
git commit -m "feat: QuestionGenerator selects conflict strategy for conflict sessions"
```

---

### Task 3: `ResolutionTracker` service

**Files:**
- Create: `backend/app/services/resolution_tracker.py`
- Test: `backend/tests/test_resolution_tracker.py`

**Interfaces:**
- Produces: `ResolutionTracker(*, llm).track(*, statement_a: str, statement_b: str, explanation: str, transcript: list[dict], same_stakeholder: bool) -> dict` returning `{"reached": bool, "decision": str | None, "statement": str | None}`. `decision` is `None` unless it is one of the four canonical values AND `reached` is truthy. Any JSON/parse error yields the not-reached dict.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_resolution_tracker.py`:

```python
import pytest

from app.services.resolution_tracker import ResolutionTracker


class Stub:
    def __init__(self, payload: str):
        self.payload = payload
        self.last_kwargs = None

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.last_kwargs = dict(temperature=temperature, response_mime_type=response_mime_type, prompt=prompt)
        return self.payload


_TRANSCRIPT = [{"role": "stakeholder", "content": "Let's just auto-approve everything."}]


@pytest.mark.asyncio
async def test_track_returns_reached_decision_and_statement():
    stub = Stub('{"reached": true, "decision": "a_wins", "statement": "Auto-approve all refunds."}')
    out = await ResolutionTracker(llm=stub).track(
        statement_a="Auto-approve all refunds.",
        statement_b="All refunds require manager sign-off.",
        explanation="Cannot both hold.",
        transcript=_TRANSCRIPT,
        same_stakeholder=True,
    )
    assert out == {"reached": True, "decision": "a_wins", "statement": "Auto-approve all refunds."}
    assert stub.last_kwargs["temperature"] == 0.2
    assert stub.last_kwargs["response_mime_type"] == "application/json"
    # both statements are shown to the model
    assert "Auto-approve all refunds." in stub.last_kwargs["prompt"]
    assert "All refunds require manager sign-off." in stub.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_track_not_reached_when_flag_false():
    stub = Stub('{"reached": false, "decision": null, "statement": null}')
    out = await ResolutionTracker(llm=stub).track(
        statement_a="A", statement_b="B", explanation="E", transcript=_TRANSCRIPT, same_stakeholder=False
    )
    assert out == {"reached": False, "decision": None, "statement": None}


@pytest.mark.asyncio
async def test_track_invalid_decision_is_not_reached():
    stub = Stub('{"reached": true, "decision": "banana", "statement": "x"}')
    out = await ResolutionTracker(llm=stub).track(
        statement_a="A", statement_b="B", explanation="E", transcript=_TRANSCRIPT, same_stakeholder=False
    )
    assert out == {"reached": False, "decision": None, "statement": None}


@pytest.mark.asyncio
async def test_track_unparseable_json_is_not_reached():
    out = await ResolutionTracker(llm=Stub("not json at all")).track(
        statement_a="A", statement_b="B", explanation="E", transcript=_TRANSCRIPT, same_stakeholder=False
    )
    assert out == {"reached": False, "decision": None, "statement": None}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_resolution_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.resolution_tracker'`.

- [ ] **Step 3: Implement the tracker**

Create `backend/app/services/resolution_tracker.py`:

```python
"""Detects whether a conflict-resolution chat has reached a resolution.

JSON-mode Gemini call (mirrors RequirementExtractor). Returns a structured stance
relative to the conflict's canonical requirement A / requirement B, or a
not-reached result on any ambiguity or parse failure — the caller treats a
not-reached result as "keep probing".
"""

import json
from typing import List

_VALID_DECISIONS = {"a_wins", "b_wins", "compromise", "restate"}
_NOT_REACHED = {"reached": False, "decision": None, "statement": None}


class ResolutionTracker:
    def __init__(self, *, llm):
        self.llm = llm

    async def track(
        self,
        *,
        statement_a: str,
        statement_b: str,
        explanation: str,
        transcript: List[dict],
        same_stakeholder: bool,
    ) -> dict:
        convo = "\n".join(f"{t['role']}: {t['content']}" for t in transcript) or "(no discussion yet)"
        whose = (
            "two requirements from the SAME stakeholder"
            if same_stakeholder
            else "requirements from two DIFFERENT stakeholders"
        )
        prompt = (
            "You are analysing a conversation in which a requirements engineer's AI is "
            f"helping resolve a conflict between {whose}.\n\n"
            f'Requirement A: "{statement_a}"\n'
            f'Requirement B: "{statement_b}"\n'
            f"Why they conflict: {explanation}\n\n"
            "Conversation so far:\n"
            f"{convo}\n\n"
            "Decide whether the stakeholder has clearly SETTLED on how to resolve the "
            "conflict. Only say reached=true when the direction is unambiguous — not when "
            "they are still weighing options or asking questions.\n"
            "Classify the resolution relative to requirement A and requirement B above:\n"
            '- "a_wins": requirement A takes priority; B is dropped or overridden.\n'
            '- "b_wins": requirement B takes priority; A is dropped or overridden.\n'
            '- "compromise": both are partly satisfied (e.g. scoped by context or threshold).\n'
            '- "restate": the stakeholder reworded the need into a single new requirement.\n'
            "When reached=true, give 'statement': one complete sentence (6-25 words) that "
            "states the resolved requirement in the same style as the originals. When "
            "reached=false, set decision and statement to null.\n\n"
            'Return JSON: {"reached": bool, "decision": "a_wins"|"b_wins"|"compromise"|"restate"|null, "statement": str|null}'
        )
        try:
            raw = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            return dict(_NOT_REACHED)

        decision = data.get("decision")
        if not data.get("reached") or decision not in _VALID_DECISIONS:
            return dict(_NOT_REACHED)
        statement = (data.get("statement") or "").strip() or None
        return {"reached": True, "decision": decision, "statement": statement}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_resolution_tracker.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/resolution_tracker.py backend/tests/test_resolution_tracker.py
git commit -m "feat: ResolutionTracker detects a reached conflict resolution"
```

---

### Task 4: Resolution schemas

**Files:**
- Modify: `backend/app/schemas/conflict.py`
- Modify: `backend/app/schemas/dialogue.py`
- Test: `backend/tests/test_resolution_schema.py`

**Interfaces:**
- Produces: `ResolutionStanceOut(stakeholder: str | None, decision: str, statement: str | None, captured_at: datetime)` in `schemas/conflict.py`; `ConflictOut.resolutions: list[ResolutionStanceOut] = []`; `ResolutionCardOut.my_resolution: ResolutionStanceOut | None = None`; `TurnResponse.resolution` and `MessageResponse.resolution: ResolutionStanceOut | None = None` in `schemas/dialogue.py`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_resolution_schema.py`:

```python
from datetime import datetime, timezone

from app.schemas.conflict import ConflictOut, RequirementRef, ResolutionCardOut, ResolutionStanceOut
from app.schemas.dialogue import MessageResponse, TurnResponse


def _stance():
    return ResolutionStanceOut(
        stakeholder="Alice", decision="a_wins", statement="Auto-approve refunds.", captured_at=datetime.now(timezone.utc)
    )


def test_resolution_stance_out_shape():
    s = _stance()
    assert s.decision == "a_wins"
    assert s.statement == "Auto-approve refunds."


def test_conflict_out_defaults_resolutions_empty():
    c = ConflictOut(
        id="1", project_id="p", status="open", explanation="e",
        requirement_a=RequirementRef(id="a", statement="A"),
        requirement_b=RequirementRef(id="b", statement="B"),
        detected_at=datetime.now(timezone.utc),
    )
    assert c.resolutions == []


def test_resolution_card_and_responses_optional_resolution():
    assert ResolutionCardOut().my_resolution is None
    assert MessageResponse(stakeholder_turn_id="t").resolution is None
    assert TurnResponse(stakeholder_turn_id="t", questions=[]).resolution is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_resolution_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'ResolutionStanceOut'`.

- [ ] **Step 3: Add schema classes and fields**

In `backend/app/schemas/conflict.py`, add after `VoteOut`:

```python
class ResolutionStanceOut(BaseModel):
    stakeholder: str | None = None
    decision: str
    statement: str | None = None
    captured_at: datetime
```

In the same file, add `resolutions` to `ConflictOut` (after `votes`) and `my_resolution` to `ResolutionCardOut`:

```python
    votes: list[VoteOut] = []
    resolutions: list[ResolutionStanceOut] = []
    detected_at: datetime
```

```python
class ResolutionCardOut(BaseModel):
    proposal: ProposalOut | None = None
    my_vote: VoteOut | None = None
    my_resolution: ResolutionStanceOut | None = None
```

In `backend/app/schemas/dialogue.py`, import the stance and add the response field:

```python
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional

from .conflict import ResolutionStanceOut
```

```python
class TurnResponse(BaseModel):
    stakeholder_turn_id: str
    questions: List[QuestionOut]
    wrap_up_suggested: bool = False
    resolution: ResolutionStanceOut | None = None


class MessageResponse(BaseModel):
    stakeholder_turn_id: str
    session_title: str | None = None
    wrap_up_suggested: bool = False
    resolution: ResolutionStanceOut | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_resolution_schema.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/conflict.py backend/app/schemas/dialogue.py backend/tests/test_resolution_schema.py
git commit -m "feat: resolution stance schema + response/card fields"
```

---

### Task 5: Capture resolution in the dialogue router

**Files:**
- Modify: `backend/app/routers/dialogue.py`
- Test: `backend/tests/test_resolution_capture.py`

**Interfaces:**
- Consumes: `ResolutionTracker` (Task 3), `ResolutionStanceOut` (Task 4), `QuestionGenerator.next_question(..., kind=)` (Task 2).
- Produces: `_make_resolution_tracker() -> ResolutionTracker`; conflict turns write `conflict.resolutions[<stakeholder_id>] = {decision, statement, session_id, captured_at}` and set the session's `wrap_up_suggested`; `/messages` and `/turns` responses carry `resolution`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_resolution_capture.py`:

```python
import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import dialogue as dialogue_mod
from tests.helpers import _re_project_and_invited_stakeholder


class FakeTracker:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def track(self, **kwargs):
        self.calls += 1
        return self.result


async def _setup_conflict_session(c):
    """RE + project + stakeholder interview session with two reqs + a conflict + a
    conflict-resolution session owned by the stakeholder. Returns (sh, uid, cid, crid)."""
    reh, sh, pid = await _re_project_and_invited_stakeholder(c)
    sh_user = await get_db().users.find_one({"email": "s@x.com"})
    uid = str(sh_user["_id"])
    sid_iv = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
    now = datetime.now(timezone.utc)
    rid_a = str((await get_db().requirements.insert_one({
        "session_id": sid_iv, "statement": "Auto-approve all refunds.",
        "type": "functional", "source_turn_id": "t", "created_at": now,
    })).inserted_id)
    rid_b = str((await get_db().requirements.insert_one({
        "session_id": sid_iv, "statement": "All refunds require manager sign-off.",
        "type": "functional", "source_turn_id": "t", "created_at": now,
    })).inserted_id)
    a, b = sorted((rid_a, rid_b))
    cid = str((await get_db().conflicts.insert_one({
        "project_id": pid, "requirement_a": a, "requirement_b": b, "pair_key": f"{a}:{b}",
        "explanation": "Cannot coexist.", "status": "open",
        "detected_at": now, "updated_at": now, "resolved_by": None,
    })).inserted_id)
    crid = str((await get_db().sessions.insert_one({
        "project_id": pid, "stakeholder_id": uid, "title": "Resolve requirement conflict",
        "kind": "conflict_resolution", "conflict_id": cid, "status": "active", "phase": "validation",
        "summary": "conflict context", "auto_named": True, "created_at": now, "updated_at": now,
    })).inserted_id)
    return sh, uid, cid, crid


@pytest.mark.asyncio
async def test_resolution_reached_captures_stance_and_pauses(monkeypatch):
    monkeypatch.setattr(
        dialogue_mod, "_make_resolution_tracker",
        lambda: FakeTracker({"reached": True, "decision": "a_wins", "statement": "Auto-approve all refunds."}),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        sh, uid, cid, crid = await _setup_conflict_session(c)
        r = await c.post(f"/sessions/{crid}/messages", json={"content": "Let's just auto-approve them."}, headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["wrap_up_suggested"] is True
        assert body["resolution"]["decision"] == "a_wins"
        assert body["resolution"]["statement"] == "Auto-approve all refunds."
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert conf["resolutions"][uid]["decision"] == "a_wins"
        assert conf["resolutions"][uid]["session_id"] == crid
        sess = await get_db().sessions.find_one({"_id": ObjectId(crid)})
        assert sess["wrap_up_suggested"] is True
        # resolution-only: no spec rows minted from the conflict chat
        assert await get_db().requirements.count_documents({"session_id": crid}) == 0


@pytest.mark.asyncio
async def test_resolution_not_reached_stores_nothing(monkeypatch):
    monkeypatch.setattr(
        dialogue_mod, "_make_resolution_tracker",
        lambda: FakeTracker({"reached": False, "decision": None, "statement": None}),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        sh, uid, cid, crid = await _setup_conflict_session(c)
        r = await c.post(f"/sessions/{crid}/messages", json={"content": "I'm not sure yet."}, headers=sh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["wrap_up_suggested"] is False
        assert body["resolution"] is None
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert conf.get("resolutions", {}) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_resolution_capture.py -v`
Expected: FAIL — `AttributeError: <module 'app.routers.dialogue'> does not have the attribute '_make_resolution_tracker'`.

- [ ] **Step 3: Add tracker factory, capture helper, and turn-processing helper**

In `backend/app/routers/dialogue.py`, add the import near the other service imports:

```python
from ..services.resolution_tracker import ResolutionTracker
from ..schemas.conflict import ResolutionStanceOut
```

Add a factory next to `_make_extractor`:

```python
def _make_resolution_tracker() -> ResolutionTracker:
    return ResolutionTracker(llm=LLMService())
```

Add these two helpers (place them right after `_extract_and_track_saturation`):

```python
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

    sess_a = await db.sessions.find_one({"_id": ObjectId(req_a["session_id"])})
    sess_b = await db.sessions.find_one({"_id": ObjectId(req_b["session_id"])})
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
```

- [ ] **Step 4: Wire the helper into `post_turn` and `post_message`, and pass `kind` to generation**

In `post_turn`, replace the `_extract_and_track_saturation` call:

```python
    wrap_up_suggested, resolution = await _process_stakeholder_turn(
        db, session, sid, stakeholder_turn_id, body.content, now
    )
```

In the `post_turn` generation loop, pass the session kind:

```python
        q = await gen.next_question(
            phase=phase, summary=summary, history=history, kind=session.get("kind", "interview")
        )
```

Update the `post_turn` return:

```python
    return TurnResponse(
        stakeholder_turn_id=stakeholder_turn_id,
        questions=questions_out,
        wrap_up_suggested=wrap_up_suggested,
        resolution=ResolutionStanceOut(**resolution) if resolution else None,
    )
```

In `post_message`, replace the `_extract_and_track_saturation` call and update the return:

```python
    wrap_up_suggested, resolution = await _process_stakeholder_turn(
        db, session, sid, stakeholder_turn_id, body.content, now
    )

    return MessageResponse(
        stakeholder_turn_id=stakeholder_turn_id,
        session_title=session_title,
        wrap_up_suggested=wrap_up_suggested,
        resolution=ResolutionStanceOut(**resolution) if resolution else None,
    )
```

In `post_question`, pass the kind:

```python
        q = await gen.next_question(
            phase=session["phase"],
            summary=summary,
            history=history,
            kind=session.get("kind", "interview"),
        )
```

- [ ] **Step 5: Run the new tests plus the existing dialogue + conflict suites**

Run: `cd backend && python -m pytest tests/test_resolution_capture.py tests/test_dialogue_router.py tests/test_conflict_resolution.py -v`
Expected: PASS. In particular `test_resolution_chat_message_creates_no_requirements` still passes — the conflict branch no longer extracts, and `_track_resolution` bails on the fake `conflict_id` before building any LLM.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/dialogue.py backend/tests/test_resolution_capture.py
git commit -m "feat: capture conflict resolution stance and pause probing on reach"
```

---

### Task 6: Surface stances via conflicts router + suggester

**Files:**
- Modify: `backend/app/routers/conflicts.py`
- Modify: `backend/app/services/resolution_suggester.py`
- Test: `backend/tests/test_resolution_suggester.py`
- Test: `backend/tests/test_resolution_surfacing.py`

**Interfaces:**
- Consumes: `ResolutionStanceOut` (Task 4); `conflict.resolutions` written in Task 5.
- Produces: `ConflictOut.resolutions` populated with stakeholder names; `ResolutionCardOut.my_resolution` for the calling stakeholder; `ResolutionSuggester.suggest(..., resolutions: list[dict] | None = None)` embeds stances in its prompt.

- [ ] **Step 1: Write the failing suggester test**

Create `backend/tests/test_resolution_suggester.py`:

```python
import pytest

from app.services.resolution_suggester import ResolutionSuggester


class Stub:
    def __init__(self, payload='{"suggestion": "Refunds under $50 auto-approve; above need sign-off.", "rationale": "Compromise."}'):
        self.payload = payload
        self.last_kwargs = None

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.last_kwargs = dict(temperature=temperature, response_mime_type=response_mime_type, prompt=prompt)
        return self.payload


@pytest.mark.asyncio
async def test_suggest_embeds_captured_stances_in_prompt():
    stub = Stub()
    out = await ResolutionSuggester(llm=stub).suggest(
        statement_a="Auto-approve all refunds.",
        statement_b="All refunds require manager sign-off.",
        explanation="Cannot both hold.",
        transcript=[{"role": "stakeholder", "content": "Maybe a threshold."}],
        same_stakeholder=True,
        resolutions=[{"decision": "compromise", "statement": "Threshold-based approval."}],
    )
    assert out["suggestion"].startswith("Refunds under $50")
    assert stub.last_kwargs["temperature"] == 0.3
    # the captured stance is surfaced to the model
    assert "Threshold-based approval." in stub.last_kwargs["prompt"]
    assert "compromise" in stub.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_suggest_without_stances_still_works():
    stub = Stub()
    out = await ResolutionSuggester(llm=stub).suggest(
        statement_a="A", statement_b="B", explanation="E",
        transcript=[], same_stakeholder=False,
    )
    assert out["rationale"] == "Compromise."
    assert "(none captured)" in stub.last_kwargs["prompt"]
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_resolution_suggester.py -v`
Expected: FAIL — `suggest() got an unexpected keyword argument 'resolutions'`.

- [ ] **Step 3: Add `resolutions` to the suggester**

In `backend/app/services/resolution_suggester.py`, update `suggest`:

```python
    async def suggest(
        self,
        *,
        statement_a: str,
        statement_b: str,
        explanation: str,
        transcript: List[dict],
        same_stakeholder: bool,
        resolutions: List[dict] | None = None,
    ) -> dict:
        convo = "\n".join(f"{t['role']}: {t['content']}" for t in transcript) or "(no discussion yet)"
        stances = "\n".join(
            f"- {s.get('decision')}: {s.get('statement') or '(no wording)'}" for s in (resolutions or [])
        ) or "(none captured)"
        whose = (
            "two requirements from the SAME stakeholder"
            if same_stakeholder
            else "requirements from two DIFFERENT stakeholders"
        )
        prompt = (
            "You are helping a requirements engineer reconcile a conflict between "
            f"{whose}.\n\n"
            f'Requirement A: "{statement_a}"\n'
            f'Requirement B: "{statement_b}"\n'
            f"Why they conflict: {explanation}\n\n"
            "Captured stakeholder resolution stance(s):\n"
            f"{stances}\n\n"
            "Conversation with the stakeholder(s) about the conflict:\n"
            f"{convo}\n\n"
            "Propose ONE reconciled requirement statement that resolves the "
            "contradiction, honoring whatever direction the conversation and the "
            "captured stance(s) settled on (one side wins, a compromise, or a "
            "restatement). Write it as a single complete sentence of roughly 6 to 25 "
            "words, in the same style as the originals. Then give a one-sentence "
            "rationale for the choice.\n\n"
            'Return JSON: {"suggestion": str, "rationale": str}'
        )
        raw = await self.llm.generate(prompt, temperature=0.3, response_mime_type="application/json")
        data = json.loads(raw)
        return {
            "suggestion": (data.get("suggestion") or "").strip(),
            "rationale": (data.get("rationale") or "").strip(),
        }
```

- [ ] **Step 4: Run the suggester test**

Run: `cd backend && python -m pytest tests/test_resolution_suggester.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing surfacing test**

Create `backend/tests/test_resolution_surfacing.py`:

```python
import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import conflicts as conflicts_mod
from tests.helpers import _re_project_and_invited_stakeholder


async def _setup_with_stance(c):
    """Build a conflict + conflict-resolution session and store one captured stance.
    Returns (reh, sh, pid, uid, cid, crid)."""
    reh, sh, pid = await _re_project_and_invited_stakeholder(c)
    sh_user = await get_db().users.find_one({"email": "s@x.com"})
    uid = str(sh_user["_id"])
    sid_iv = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
    now = datetime.now(timezone.utc)
    rid_a = str((await get_db().requirements.insert_one({
        "session_id": sid_iv, "statement": "Auto-approve all refunds.",
        "type": "functional", "source_turn_id": "t", "created_at": now,
    })).inserted_id)
    rid_b = str((await get_db().requirements.insert_one({
        "session_id": sid_iv, "statement": "All refunds require manager sign-off.",
        "type": "functional", "source_turn_id": "t", "created_at": now,
    })).inserted_id)
    a, b = sorted((rid_a, rid_b))
    cid = str((await get_db().conflicts.insert_one({
        "project_id": pid, "requirement_a": a, "requirement_b": b, "pair_key": f"{a}:{b}",
        "explanation": "Cannot coexist.", "status": "open",
        "detected_at": now, "updated_at": now, "resolved_by": None,
        "resolutions": {uid: {"decision": "a_wins", "statement": "Auto-approve all refunds.",
                              "session_id": "seed", "captured_at": now}},
    })).inserted_id)
    crid = str((await get_db().sessions.insert_one({
        "project_id": pid, "stakeholder_id": uid, "title": "Resolve requirement conflict",
        "kind": "conflict_resolution", "conflict_id": cid, "status": "active", "phase": "validation",
        "summary": "ctx", "auto_named": True, "created_at": now, "updated_at": now,
    })).inserted_id)
    return reh, sh, pid, uid, cid, crid


@pytest.mark.asyncio
async def test_conflict_out_includes_resolutions_with_names():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, uid, cid, crid = await _setup_with_stance(c)
        r = await c.get(f"/projects/{pid}/conflicts", headers=reh)
        assert r.status_code == 200, r.text
        item = r.json()[0]
        assert len(item["resolutions"]) == 1
        stance = item["resolutions"][0]
        assert stance["decision"] == "a_wins"
        assert stance["statement"] == "Auto-approve all refunds."
        assert stance["stakeholder"] == "S"  # real_name from the invited stakeholder


@pytest.mark.asyncio
async def test_resolution_card_includes_my_resolution():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, uid, cid, crid = await _setup_with_stance(c)
        r = await c.get(f"/sessions/{crid}/resolution", headers=sh)
        assert r.status_code == 200, r.text
        card = r.json()
        assert card["my_resolution"]["decision"] == "a_wins"
        assert card["my_resolution"]["statement"] == "Auto-approve all refunds."
```

- [ ] **Step 6: Run to verify failure**

Run: `cd backend && python -m pytest tests/test_resolution_surfacing.py -v`
Expected: FAIL — `resolutions` missing from the conflict payload / `my_resolution` is null.

- [ ] **Step 7: Populate `resolutions` and `my_resolution`, and feed the suggester**

In `backend/app/routers/conflicts.py`, import the stance schema (add to the existing `..schemas.conflict` import list):

```python
    ResolutionStanceOut,
```

In `_conflict_to_out`, build the stance list and pass it to `ConflictOut`. Add before the `return ConflictOut(...)`:

```python
    resolutions_out: list[ResolutionStanceOut] = []
    for uid, stance in (doc.get("resolutions") or {}).items():
        resolutions_out.append(
            ResolutionStanceOut(
                stakeholder=await _uid_to_name(db, uid),
                decision=stance.get("decision"),
                statement=stance.get("statement"),
                captured_at=stance.get("captured_at"),
            )
        )
```

and add `resolutions=resolutions_out,` to the `ConflictOut(...)` call (next to `votes=votes_out,`).

In `get_resolution_card`, resolve the caller's own stance. Replace the final return:

```python
    mine = (conflict.get("votes") or {}).get(user["_id"])
    my_stance = (conflict.get("resolutions") or {}).get(user["_id"])
    return ResolutionCardOut(
        proposal=ProposalOut(**proposal) if proposal else None,
        my_vote=VoteOut(stakeholder=None, **mine) if mine else None,
        my_resolution=ResolutionStanceOut(
            stakeholder=None,
            decision=my_stance["decision"],
            statement=my_stance.get("statement"),
            captured_at=my_stance["captured_at"],
        ) if my_stance else None,
    )
```

In `suggest_resolution`, pass the captured stances to the suggester. Update the `.suggest(...)` call:

```python
        result = await _make_suggester().suggest(
            statement_a=req_a["statement"],
            statement_b=req_b["statement"],
            explanation=conflict.get("explanation", ""),
            transcript=await _resolution_transcript(db, cid),
            same_stakeholder=same,
            resolutions=list((conflict.get("resolutions") or {}).values()),
        )
```

- [ ] **Step 8: Run the surfacing + full conflict suites**

Run: `cd backend && python -m pytest tests/test_resolution_surfacing.py tests/test_conflicts_router.py tests/test_conflict_resolution.py -v`
Expected: PASS (existing suggester/vote/list tests unaffected — `FakeSuggester.suggest(**kwargs)` accepts the new `resolutions` kwarg; `ResolutionCardOut` gains an optional field).

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/conflicts.py backend/app/services/resolution_suggester.py backend/tests/test_resolution_suggester.py backend/tests/test_resolution_surfacing.py
git commit -m "feat: expose resolution stances on conflicts, card, and suggester"
```

---

### Task 7: Frontend API types + `resolutionLabel`

**Files:**
- Modify: `frontend/src/api/conflicts.ts`
- Modify: `frontend/src/api/sessions.ts:41-47`
- Create: `frontend/src/components/Conflicts/resolutionLabel.ts`
- Test: `frontend/src/components/Conflicts/resolutionLabel.test.ts`

**Interfaces:**
- Produces: TS type `ResolutionStance = { stakeholder: string | null; decision: string; statement: string | null; captured_at: string }`; `Conflict.resolutions: ResolutionStance[]`; `ResolutionCard.my_resolution: ResolutionStance | null`; `postMessage` response `resolution?: ResolutionStance | null`; `resolutionLabel(decision: string): string`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/Conflicts/resolutionLabel.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { resolutionLabel } from "./resolutionLabel";

describe("resolutionLabel", () => {
  it("labels each decision", () => {
    expect(resolutionLabel("a_wins")).toBe("Prioritize the first requirement");
    expect(resolutionLabel("b_wins")).toBe("Prioritize the second requirement");
    expect(resolutionLabel("compromise")).toBe("Compromise");
    expect(resolutionLabel("restate")).toBe("Restated requirement");
  });

  it("falls back for an unknown decision", () => {
    expect(resolutionLabel("something_else")).toBe("Resolution recorded");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/components/Conflicts/resolutionLabel.test.ts`
Expected: FAIL — cannot find module `./resolutionLabel`.

- [ ] **Step 3: Implement `resolutionLabel`**

Create `frontend/src/components/Conflicts/resolutionLabel.ts`:

```ts
export function resolutionLabel(decision: string): string {
  switch (decision) {
    case "a_wins":
      return "Prioritize the first requirement";
    case "b_wins":
      return "Prioritize the second requirement";
    case "compromise":
      return "Compromise";
    case "restate":
      return "Restated requirement";
    default:
      return "Resolution recorded";
  }
}
```

- [ ] **Step 4: Add the API types**

In `frontend/src/api/conflicts.ts`, add the `ResolutionStance` type (after `ResolutionVote`) and extend `Conflict` and `ResolutionCard`:

```ts
export type ResolutionStance = {
  stakeholder: string | null;
  decision: string;
  statement: string | null;
  captured_at: string;
};
```

```ts
export type Conflict = {
  id: string;
  project_id: string;
  status: "open" | "resolved" | "dismissed";
  explanation: string;
  requirement_a: RequirementRef;
  requirement_b: RequirementRef;
  resolution_sessions: ResolutionSessionRef[];
  proposal: ResolutionProposal | null;
  votes: ResolutionVote[];
  resolutions: ResolutionStance[];
  detected_at: string;
};
```

```ts
export type ResolutionCard = {
  proposal: ResolutionProposal | null;
  my_vote: ResolutionVote | null;
  my_resolution: ResolutionStance | null;
};
```

In `frontend/src/api/sessions.ts`, import the stance type and add `resolution` to the `postMessage` response:

```ts
import { api } from "./client";
import type { ResolutionStance } from "./conflicts";
```

```ts
export const postMessage = (id: string, content: string) =>
  api
    .post<{
      stakeholder_turn_id: string;
      session_title?: string | null;
      wrap_up_suggested?: boolean;
      resolution?: ResolutionStance | null;
    }>(`/sessions/${id}/messages`, { content })
    .then((r) => r.data);
```

- [ ] **Step 5: Run the test + typecheck**

Run: `cd frontend && npx vitest run src/components/Conflicts/resolutionLabel.test.ts`
Expected: PASS (2 tests).
Run: `cd frontend && npx tsc -b`
Expected: no type errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/conflicts.ts frontend/src/api/sessions.ts frontend/src/components/Conflicts/resolutionLabel.ts frontend/src/components/Conflicts/resolutionLabel.test.ts
git commit -m "feat: frontend resolution types + label helper"
```

---

### Task 8: Stakeholder "Resolution recorded" card + kind-aware wrap-up banner

**Files:**
- Create: `frontend/src/components/Dialogue/ResolutionRecordedCard.tsx`
- Modify: `frontend/src/pages/MainPage.tsx:106-115`
- Modify: `frontend/src/components/Dialogue/InputBox.tsx:175-198`

**Interfaces:**
- Consumes: `getResolutionCard` (returns `my_resolution` from Task 6), `resolutionLabel` (Task 7), `Session.kind` (already on the `Session` type).
- Produces: an in-chat card shown to the stakeholder once a resolution is captured; conflict-appropriate wrap-up copy.

- [ ] **Step 1: Create the card component**

Create `frontend/src/components/Dialogue/ResolutionRecordedCard.tsx`:

```tsx
import { useEffect, useState } from "react";
import { getResolutionCard, type ResolutionStance } from "../../api/conflicts";
import { resolutionLabel } from "../Conflicts/resolutionLabel";

// Self-contained: fetches the captured resolution stance for this conflict session.
// Renders nothing for interview sessions (the endpoint 404s) or before a resolution
// has been captured.
export default function ResolutionRecordedCard({ sessionId }: { sessionId: string }) {
  const [stance, setStance] = useState<ResolutionStance | null>(null);

  // Fetch on session change, then poll — the stance is written mid-conversation by
  // the backend, so a one-shot fetch would miss it (mirrors MainPage's poll cadence).
  useEffect(() => {
    let alive = true;
    setStance(null);
    const fetchStance = () =>
      getResolutionCard(sessionId)
        .then((c) => {
          if (alive) setStance(c.my_resolution);
        })
        .catch(() => {
          if (alive) setStance(null);
        });
    fetchStance();
    const id = setInterval(() => {
      if (!document.hidden) fetchStance();
    }, 6000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [sessionId]);

  if (!stance) return null;

  return (
    <div className="mx-6 mb-3 rounded-xl border border-border bg-surface p-3 shadow-card space-y-1">
      <p className="text-xs font-medium text-accent">Resolution recorded ✓</p>
      <p className="text-xs text-muted">{resolutionLabel(stance.decision)}</p>
      {stance.statement && <p className="text-sm text-foreground">{stance.statement}</p>}
      <p className="text-xs text-muted">Shared with your requirements engineer.</p>
    </div>
  );
}
```

- [ ] **Step 2: Render it in the stakeholder view**

In `frontend/src/pages/MainPage.tsx`, add the import:

```tsx
import ResolutionRecordedCard from "../components/Dialogue/ResolutionRecordedCard";
```

In the stakeholder (`else`) branch, render the card above the vote card:

```tsx
          <main className="flex min-h-0 flex-col overflow-hidden bg-surface-muted">
            <ChatPanel />
            {activeId && <ResolutionRecordedCard sessionId={activeId} />}
            {activeId && <ResolutionVoteCard sessionId={activeId} />}
            <InputBox />
          </main>
```

- [ ] **Step 3: Make the wrap-up banner kind-aware**

In `frontend/src/components/Dialogue/InputBox.tsx`, the `activeSession` is already computed at line 50. Update the banner text (the `<span>` inside the `{wrapUp && ...}` block) to switch on kind:

```tsx
          <span>
            {activeSession?.kind === "conflict_resolution"
              ? "Sounds like you've settled on a direction — confirm it, or keep discussing?"
              : "It sounds like we've covered a lot — anything else you'd like to add, or shall we wrap up?"}
          </span>
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npx tsc -b`
Expected: no type errors.

- [ ] **Step 5: Verify in the preview (manual)**

To verify the UI deterministically (independent of the live Gemini tracker), seed a stance directly, then open the stakeholder's conflict chat:

```
db.conflicts.updateOne(
  { _id: <conflictId> },
  { $set: { "resolutions.<stakeholderUserId>": { decision: "a_wins", statement: "Auto-approve all refunds.", session_id: "<resolutionSessionId>", captured_at: new Date() } } }
)
```

Confirm the "Resolution recorded ✓" card appears within ~6s (poll cadence). Then, in a live run, send a settling message and confirm the wrap-up banner shows the conflict copy. Capture a screenshot for the PR.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Dialogue/ResolutionRecordedCard.tsx frontend/src/pages/MainPage.tsx frontend/src/components/Dialogue/InputBox.tsx
git commit -m "feat: stakeholder resolution-recorded card + conflict wrap-up copy"
```

---

### Task 9: RE-side resolution panel + `matchConflictForSession`

**Files:**
- Create: `frontend/src/components/Conflicts/matchConflictForSession.ts`
- Test: `frontend/src/components/Conflicts/matchConflictForSession.test.ts`
- Create: `frontend/src/components/Requirements/ConflictResolutionPanel.tsx`
- Modify: `frontend/src/pages/MainPage.tsx:33-46,97-105`

**Interfaces:**
- Consumes: `listConflicts` (returns `resolutions`, Task 6), `resolutionLabel` (Task 7), `matchConflictForSession`.
- Produces: `matchConflictForSession(conflicts: Conflict[], sessionId: string): Conflict | null`; a right-hand panel for the RE that replaces `LiveRequirements` when the active session is a conflict session.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/Conflicts/matchConflictForSession.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { matchConflictForSession } from "./matchConflictForSession";
import type { Conflict } from "../../api/conflicts";

const conflict = (id: string, sessionIds: string[]): Conflict => ({
  id,
  project_id: "p",
  status: "open",
  explanation: "e",
  requirement_a: { id: "a", statement: "A", stakeholder: null },
  requirement_b: { id: "b", statement: "B", stakeholder: null },
  resolution_sessions: sessionIds.map((sid) => ({ id: sid, stakeholder: null })),
  proposal: null,
  votes: [],
  resolutions: [],
  detected_at: "2026-01-01T00:00:00Z",
});

describe("matchConflictForSession", () => {
  it("finds the conflict whose resolution sessions include the id", () => {
    const conflicts = [conflict("c1", ["s1", "s2"]), conflict("c2", ["s3"])];
    expect(matchConflictForSession(conflicts, "s3")?.id).toBe("c2");
  });

  it("returns null when no conflict matches", () => {
    expect(matchConflictForSession([conflict("c1", ["s1"])], "sX")).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/components/Conflicts/matchConflictForSession.test.ts`
Expected: FAIL — cannot find module `./matchConflictForSession`.

- [ ] **Step 3: Implement the matcher**

Create `frontend/src/components/Conflicts/matchConflictForSession.ts`:

```ts
import type { Conflict } from "../../api/conflicts";

export function matchConflictForSession(
  conflicts: Conflict[],
  sessionId: string
): Conflict | null {
  return (
    conflicts.find((c) => c.resolution_sessions.some((rs) => rs.id === sessionId)) ?? null
  );
}
```

- [ ] **Step 4: Create the RE panel**

Create `frontend/src/components/Requirements/ConflictResolutionPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { listConflicts, type Conflict } from "../../api/conflicts";
import { matchConflictForSession } from "../Conflicts/matchConflictForSession";
import { resolutionLabel } from "../Conflicts/resolutionLabel";

// The RE's right-hand panel while observing a conflict-resolution chat: shows the
// two clashing requirements and any resolution stances captured from stakeholders.
export default function ConflictResolutionPanel({
  projectId,
  sessionId,
}: {
  projectId: string;
  sessionId: string;
}) {
  const [conflict, setConflict] = useState<Conflict | null>(null);

  // Fetch then poll, so a stance captured while the RE watches this chat appears
  // without a manual reload (mirrors ConflictsPanel's polling cadence).
  useEffect(() => {
    let alive = true;
    const fetchConflict = () =>
      listConflicts(projectId)
        .then((all) => {
          if (alive) setConflict(matchConflictForSession(all, sessionId));
        })
        .catch(() => {
          if (alive) setConflict(null);
        });
    fetchConflict();
    const id = setInterval(() => {
      if (!document.hidden) fetchConflict();
    }, 6000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [projectId, sessionId]);

  return (
    <aside className="flex min-h-0 flex-col gap-3.5 overflow-y-auto border-l border-border bg-surface p-4">
      <h2 className="shrink-0 text-sm font-semibold text-foreground">Resolution</h2>
      {!conflict ? (
        <p className="text-sm italic text-muted">No conflict data for this chat.</p>
      ) : (
        <>
          <div className="shrink-0 space-y-2 rounded-xl border border-border bg-surface p-3">
            <p className="text-xs font-medium text-accent">Conflicting requirements</p>
            <p className="text-sm text-foreground">A: {conflict.requirement_a.statement}</p>
            <p className="text-sm text-foreground">B: {conflict.requirement_b.statement}</p>
            <p className="text-xs italic text-muted">{conflict.explanation}</p>
          </div>
          <div className="shrink-0 space-y-2">
            <p className="text-xs font-semibold text-foreground">Captured resolutions</p>
            {conflict.resolutions.length === 0 ? (
              <p className="text-sm italic text-muted">No resolution captured yet.</p>
            ) : (
              conflict.resolutions.map((s, i) => (
                <div key={i} className="rounded-lg border border-border bg-background p-3 space-y-1">
                  <p className="text-xs font-medium text-accent">{s.stakeholder ?? "Stakeholder"}</p>
                  <p className="text-xs text-muted">{resolutionLabel(s.decision)}</p>
                  {s.statement && <p className="text-sm text-foreground">{s.statement}</p>}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </aside>
  );
}
```

- [ ] **Step 5: Swap the panel for conflict sessions in the RE view**

In `frontend/src/pages/MainPage.tsx`, add the import:

```tsx
import ConflictResolutionPanel from "../components/Requirements/ConflictResolutionPanel";
```

Track the active session's kind alongside `projectId`. Add state and set it in the existing RE effect:

```tsx
  const [projectId, setProjectId] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<string | null>(null);
```

```tsx
    listAllSessions()
      .then((all) => {
        if (!active) return;
        const s = all.find((x) => x.id === activeId);
        if (s) {
          setProjectId(s.project_id);
          setActiveKind(s.kind ?? null);
        }
      })
      .catch(() => {});
```

In the RE branch JSX, replace `<LiveRequirements />` with the conditional:

```tsx
          {activeKind === "conflict_resolution" && projectId && activeId ? (
            <ConflictResolutionPanel projectId={projectId} sessionId={activeId} />
          ) : (
            <LiveRequirements />
          )}
```

- [ ] **Step 6: Run test + typecheck**

Run: `cd frontend && npx vitest run src/components/Conflicts/matchConflictForSession.test.ts`
Expected: PASS (2 tests).
Run: `cd frontend && npx tsc -b`
Expected: no type errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Conflicts/matchConflictForSession.ts frontend/src/components/Conflicts/matchConflictForSession.test.ts frontend/src/components/Requirements/ConflictResolutionPanel.tsx frontend/src/pages/MainPage.tsx
git commit -m "feat: RE conflict-resolution side panel shows captured stances"
```

---

### Task 10: Show captured stances in the RE Conflicts panel

**Files:**
- Modify: `frontend/src/components/Conflicts/ConflictsPanel.tsx:234-251`

**Interfaces:**
- Consumes: `Conflict.resolutions` (Task 6/7), `resolutionLabel` (Task 7).
- Produces: a per-stakeholder stance block under each conflict on the project page.

- [ ] **Step 1: Add the import**

In `frontend/src/components/Conflicts/ConflictsPanel.tsx`, add:

```tsx
import { resolutionLabel } from "./resolutionLabel";
```

- [ ] **Step 2: Render the stances**

Immediately after the `{c.resolution_sessions.length > 0 && ( ... )}` block (before the `{c.proposal && ( ... )}` block), add:

```tsx
              {c.resolutions.length > 0 && (
                <div className="space-y-1 rounded-md border border-dashed border-border bg-surface px-2 py-1.5 text-xs">
                  <p className="text-muted">Captured resolutions:</p>
                  {c.resolutions.map((s, i) => (
                    <p key={i} className="text-foreground">
                      {s.stakeholder ?? "Stakeholder"}: {resolutionLabel(s.decision)}
                      {s.statement ? ` — "${s.statement}"` : ""}
                    </p>
                  ))}
                </div>
              )}
```

- [ ] **Step 3: Typecheck + build**

Run: `cd frontend && npx tsc -b`
Expected: no type errors.
Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Verify in the preview (manual)**

Open the project page as the RE with a conflict that has a captured stance (from Task 5 or seeded). Confirm the "Captured resolutions" block renders under the conflict. Screenshot for the PR.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Conflicts/ConflictsPanel.tsx
git commit -m "feat: show captured resolution stances in RE conflicts panel"
```

---

## Final verification

- [ ] **Backend — full suite**

Run: `cd backend && python -m pytest -q`
Expected: all tests pass.

- [ ] **Frontend — tests, types, build**

Run: `cd frontend && npx vitest run && npx tsc -b && npm run build`
Expected: tests pass, no type errors, build succeeds.

- [ ] **End-to-end sanity (manual, preview)**

As the RE: detect a conflict, open a stakeholder's resolution chat. As the stakeholder: answer the goal-directed probes and settle on a direction; confirm the "Resolution recorded ✓" card appears and probing pauses. As the RE: confirm the captured stance shows in both the in-chat Resolution panel and the project Conflicts panel, and that "Suggest reconciled wording" now reflects the stance.
