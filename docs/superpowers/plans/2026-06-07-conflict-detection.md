# Cross-Stakeholder Conflict Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect and surface direct contradictions between requirements gathered from different stakeholders in a project, so the requirements engineer can resolve them.

**Architecture:** A new project-level analysis layer over the existing per-session requirement extraction. A `ConflictDetector` service makes a single-pass Gemini JSON call over all of a project's requirements (each tagged with its stakeholder); an SRE-only router stores results in a `conflicts` collection keyed by a stable `pair_key` (so re-runs don't duplicate and dismissed pairs stay suppressed); a Conflicts panel on the project page lets the engineer detect, then resolve or dismiss each conflict.

**Tech Stack:** Python / FastAPI / Motor (MongoDB) on the backend with Google Gemini via the existing `LLMService`; React / TypeScript / Axios / Tailwind on the frontend. Backend tests use pytest + httpx `AsyncClient` with an injected fake LLM.

**Spec:** `docs/superpowers/specs/2026-06-07-conflict-detection-design.md`

---

### Task 1: `ConflictDetector` service

Pure service, no DB. Takes a list of requirement dicts, returns contradicting pairs as real requirement-id pairs. Mirrors `RequirementExtractor`.

**Files:**
- Create: `backend/app/services/conflict_detector.py`
- Test: `backend/tests/test_conflict_detector.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_conflict_detector.py
import pytest
from app.services.conflict_detector import ConflictDetector


class Stub:
    def __init__(self, payload: str):
        self.payload = payload
        self.last_kwargs = None

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.last_kwargs = dict(
            temperature=temperature,
            response_mime_type=response_mime_type,
            prompt=prompt,
        )
        return self.payload


def _reqs():
    return [
        {"id": "aaa", "statement": "Auto-approve all refunds.", "stakeholder": "Alice", "type": "functional"},
        {"id": "bbb", "statement": "All refunds require manager sign-off.", "stakeholder": "Bob", "type": "functional"},
        {"id": "ccc", "statement": "Support dark mode.", "stakeholder": "Bob", "type": "functional"},
    ]


@pytest.mark.asyncio
async def test_detect_maps_indices_to_requirement_ids():
    stub = Stub('{"conflicts": [{"a": 0, "b": 1, "explanation": "Cannot both auto-approve and require sign-off."}]}')
    det = ConflictDetector(llm=stub)
    out = await det.detect(_reqs())
    assert len(out) == 1
    # ids are returned sorted so requirement_a <= requirement_b
    assert out[0]["requirement_a"] == "aaa"
    assert out[0]["requirement_b"] == "bbb"
    assert "sign-off" in out[0]["explanation"]
    assert stub.last_kwargs["temperature"] == 0.2
    assert stub.last_kwargs["response_mime_type"] == "application/json"
    # the prompt must label requirements with their stakeholder
    assert "Alice" in stub.last_kwargs["prompt"]
    assert "Bob" in stub.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_detect_returns_empty_when_no_conflicts():
    det = ConflictDetector(llm=Stub('{"conflicts": []}'))
    assert await det.detect(_reqs()) == []


@pytest.mark.asyncio
async def test_detect_returns_empty_for_fewer_than_two_requirements():
    det = ConflictDetector(llm=Stub('{"conflicts": [{"a": 0, "b": 0, "explanation": "x"}]}'))
    assert await det.detect([{"id": "only", "statement": "x", "stakeholder": "A", "type": "functional"}]) == []


@pytest.mark.asyncio
async def test_detect_drops_malformed_and_out_of_range_pairs():
    payload = (
        '{"conflicts": ['
        '{"a": 0, "b": 99, "explanation": "out of range"},'      # b out of range
        '{"a": 1, "b": 1, "explanation": "self pair"},'          # a == b
        '{"a": "x", "b": 2, "explanation": "non-int"},'          # non-int index
        '{"explanation": "missing indices"}'                     # missing a/b
        ']}'
    )
    det = ConflictDetector(llm=Stub(payload))
    assert await det.detect(_reqs()) == []


@pytest.mark.asyncio
async def test_detect_returns_empty_on_unparseable_json():
    det = ConflictDetector(llm=Stub("not json at all"))
    assert await det.detect(_reqs()) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && pytest tests/test_conflict_detector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.conflict_detector'`

- [ ] **Step 3: Write the implementation**

```python
# backend/app/services/conflict_detector.py
import json
from typing import List


class ConflictDetector:
    """Finds pairs of directly contradicting requirements via a single JSON-mode Gemini call.

    Input requirements are dicts: {"id": str, "statement": str, "stakeholder": str|None, "type": str}.
    Output pairs are dicts: {"requirement_a": str, "requirement_b": str, "explanation": str},
    where requirement_a/_b are the original ids, sorted so requirement_a <= requirement_b.
    """

    def __init__(self, *, llm):
        self.llm = llm

    async def detect(self, requirements: List[dict]) -> List[dict]:
        if len(requirements) < 2:
            return []

        numbered = "\n".join(
            f'{i}. [{r.get("stakeholder") or "Unknown"}] {r["statement"]}'
            for i, r in enumerate(requirements)
        )

        prompt = (
            "You are reviewing software requirements gathered from MULTIPLE stakeholders.\n"
            "Each line is numbered and tagged with the stakeholder who stated it:\n"
            "    <index>. [<stakeholder>] <requirement>\n\n"
            "Find pairs of requirements that DIRECTLY CONTRADICT each other — pairs that\n"
            "cannot both be satisfied in the same system (e.g. 'auto-approve refunds' vs\n"
            "'all refunds require manager sign-off').\n\n"
            "STRICT RULES:\n"
            "- Report ONLY direct contradictions. Do NOT report requirements that are merely\n"
            "  different, related, overlapping, redundant, or vague. If two requirements can\n"
            "  both hold at once, they are NOT a conflict.\n"
            "- Prefer precision: when in doubt, do NOT report a pair.\n"
            "- Reference requirements by their integer index from the list.\n"
            "- Each explanation is ONE sentence stating why the two cannot coexist.\n\n"
            'Return JSON: {"conflicts": [{"a": <int>, "b": <int>, "explanation": <str>}]}\n'
            "If there are no contradictions, return an empty list.\n\n"
            f"Requirements:\n{numbered}"
        )

        raw = await self.llm.generate(
            prompt, temperature=0.2, response_mime_type="application/json"
        )
        try:
            pairs = json.loads(raw).get("conflicts", [])
        except (ValueError, TypeError):
            return []

        n = len(requirements)
        seen: set[tuple[str, str]] = set()
        out: List[dict] = []
        for p in pairs:
            a = p.get("a")
            b = p.get("b")
            if not isinstance(a, int) or not isinstance(b, int):
                continue
            if a == b or not (0 <= a < n) or not (0 <= b < n):
                continue
            id_a = requirements[a]["id"]
            id_b = requirements[b]["id"]
            key = tuple(sorted((id_a, id_b)))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "requirement_a": key[0],
                    "requirement_b": key[1],
                    "explanation": p.get("explanation") or "",
                }
            )
        return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_conflict_detector.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/conflict_detector.py backend/tests/test_conflict_detector.py
git commit -m "feat: add ConflictDetector service for cross-stakeholder contradiction detection"
```

---

### Task 2: Conflict schemas

Pydantic response/request models for the router.

**Files:**
- Create: `backend/app/schemas/conflict.py`

- [ ] **Step 1: Write the schemas**

```python
# backend/app/schemas/conflict.py
from datetime import datetime

from pydantic import BaseModel


class RequirementRef(BaseModel):
    id: str
    statement: str
    stakeholder: str | None = None


class ConflictOut(BaseModel):
    id: str
    project_id: str
    status: str
    explanation: str
    requirement_a: RequirementRef
    requirement_b: RequirementRef
    detected_at: datetime


class ConflictPatch(BaseModel):
    status: str
```

- [ ] **Step 2: Verify it imports**

Run: `cd backend && python -c "from app.schemas.conflict import ConflictOut, ConflictPatch, RequirementRef; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/conflict.py
git commit -m "feat: add conflict response/request schemas"
```

---

### Task 3: Conflicts router — detect endpoint + helpers + registration

Adds the router with shared helpers and the `POST /projects/{pid}/conflicts/detect` endpoint, registers it in `main.py`, and adds the `conflicts` indexes. SRE-only and ownership-checked.

**Files:**
- Create: `backend/app/routers/conflicts.py`
- Modify: `backend/app/main.py` (import + `include_router`)
- Modify: `backend/app/db/mongo.py:19-31` (add conflicts indexes inside `init_indexes`)
- Test: `backend/tests/test_conflicts_router.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_conflicts_router.py
import pytest
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.mongo import get_db
from app.routers import conflicts as conflicts_mod


class FakeDetector:
    """Returns a fixed list of {requirement_a, requirement_b, explanation} pairs."""

    def __init__(self, pairs):
        self._pairs = pairs

    async def detect(self, requirements):
        return self._pairs


async def _create_re(c, email: str):
    await c.post("/auth/signup", json={"email": email, "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": email}, {"$set": {"role": "requirements_engineer"}})
    tok = (await c.post("/auth/login", json={"email": email, "password": "Passw0rd!"})).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _setup_project_with_two_reqs(c, re_email, sh_email, sh_name="Alice"):
    """RE + project + one stakeholder session + two requirements in that session.

    Returns (re_headers, project_id, session_id, [rid_a, rid_b]).
    """
    reh = await _create_re(c, re_email)
    pid = (await c.post("/projects", json={"title": "Conflict Test"}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": sh_email}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": sh_name})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]

    now = datetime.now(timezone.utc)
    rid_a = str((await get_db().requirements.insert_one({
        "session_id": sid, "statement": "Auto-approve all refunds.",
        "type": "functional", "source_turn_id": "t1", "created_at": now,
    })).inserted_id)
    rid_b = str((await get_db().requirements.insert_one({
        "session_id": sid, "statement": "All refunds require manager sign-off.",
        "type": "functional", "source_turn_id": "t2", "created_at": now,
    })).inserted_id)
    return reh, pid, sid, [rid_a, rid_b]


@pytest.mark.asyncio
async def test_detect_stores_and_returns_open_conflicts(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c1@x.com", "sh_c1@x.com", sh_name="Alice"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        item = body[0]
        assert item["status"] == "open"
        assert item["explanation"] == "Cannot coexist."
        statements = {item["requirement_a"]["statement"], item["requirement_b"]["statement"]}
        assert "Auto-approve all refunds." in statements
        # stakeholder name resolved from the session
        assert item["requirement_a"]["stakeholder"] == "Alice"


@pytest.mark.asyncio
async def test_detect_is_idempotent_no_duplicate_rows(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c2@x.com", "sh_c2@x.com"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        count = await get_db().conflicts.count_documents({"project_id": pid})
        assert count == 1


@pytest.mark.asyncio
async def test_detect_requires_sre_role(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c3@x.com", "sh_c3@x.com"
        )
        # log in as the stakeholder
        s_tok = (await c.post("/auth/login", json={"email": "sh_c3@x.com", "password": "Stake123!"})).json()["access_token"]
        sh = {"Authorization": f"Bearer {s_tok}"}
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=sh)
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_detect_on_unowned_project_returns_404(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, _ = await _setup_project_with_two_reqs(
            c, "re_c4@x.com", "sh_c4@x.com"
        )
        re2h = await _create_re(c, "re_c4b@x.com")
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=re2h)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_detect_returns_503_when_llm_unavailable(monkeypatch):
    from app.services.llm_service import UpstreamUnavailable

    class FailingDetector:
        async def detect(self, requirements):
            raise UpstreamUnavailable("Gemini is temporarily overloaded.")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, _ = await _setup_project_with_two_reqs(
            c, "re_c4c@x.com", "sh_c4c@x.com"
        )
        monkeypatch.setattr(conflicts_mod, "_make_detector", lambda: FailingDetector())
        r = await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        assert r.status_code == 503, r.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && pytest tests/test_conflicts_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.conflicts'` (collection error)

- [ ] **Step 3: Create the router**

```python
# backend/app/routers/conflicts.py
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
```

- [ ] **Step 4: Register the router in `main.py`**

In `backend/app/main.py`, add the import alongside the other router imports (after line 12):

```python
from .routers import conflicts as conflicts_router
```

And add the registration alongside the other `include_router` calls (after line 28):

```python
app.include_router(conflicts_router.router)
```

- [ ] **Step 5: Add conflicts indexes in `mongo.py`**

In `backend/app/db/mongo.py`, inside `init_indexes`, add these two lines just before the closing of the function (after the `invitations` indexes):

```python
    await db.conflicts.create_index([("project_id", 1), ("pair_key", 1)], unique=True)
    await db.conflicts.create_index([("project_id", 1), ("status", 1)])
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd backend && pytest tests/test_conflicts_router.py -v`
Expected: PASS (5 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/conflicts.py backend/app/main.py backend/app/db/mongo.py backend/tests/test_conflicts_router.py
git commit -m "feat: add conflict detect endpoint with pair_key dedup and ownership checks"
```

---

### Task 4: List endpoint + stale hiding

Adds `GET /projects/{pid}/conflicts` and proves stale conflicts (referencing a deleted/rejected requirement) are hidden. The `_list_conflicts` helper already filters stale; this task wires the endpoint and tests it.

**Files:**
- Modify: `backend/app/routers/conflicts.py` (add the GET endpoint)
- Test: `backend/tests/test_conflicts_router.py` (append tests)

- [ ] **Step 1: Write the failing tests (append to the test file)**

```python
@pytest.mark.asyncio
async def test_list_conflicts_returns_stored_open_conflicts(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c5@x.com", "sh_c5@x.com"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        r = await c.get(f"/projects/{pid}/conflicts", headers=reh)
        assert r.status_code == 200, r.text
        assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_list_hides_stale_conflict_when_requirement_rejected(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c6@x.com", "sh_c6@x.com"
        )
        a, b = sorted((rid_a, rid_b))
        monkeypatch.setattr(
            conflicts_mod, "_make_detector",
            lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
        )
        await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)
        # Reject one of the referenced requirements
        await c.patch(f"/requirements/{rid_a}", json={"status": "rejected"}, headers=reh)
        r = await c.get(f"/projects/{pid}/conflicts", headers=reh)
        assert r.status_code == 200, r.text
        assert r.json() == []


@pytest.mark.asyncio
async def test_list_on_unowned_project_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, _ = await _setup_project_with_two_reqs(
            c, "re_c7@x.com", "sh_c7@x.com"
        )
        re2h = await _create_re(c, "re_c7b@x.com")
        r = await c.get(f"/projects/{pid}/conflicts", headers=re2h)
        assert r.status_code == 404, r.text
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && pytest tests/test_conflicts_router.py -k "list_conflicts or stale or list_on_unowned" -v`
Expected: FAIL — `405 Method Not Allowed` / `404` from missing GET route (the GET endpoint does not exist yet)

- [ ] **Step 3: Add the GET endpoint**

Append to `backend/app/routers/conflicts.py` (after `detect_conflicts`):

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && pytest tests/test_conflicts_router.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/conflicts.py backend/tests/test_conflicts_router.py
git commit -m "feat: add list conflicts endpoint with stale-conflict hiding"
```

---

### Task 5: Patch endpoint — resolve / dismiss

Adds `PATCH /conflicts/{cid}`. Proves status transitions, ownership, validation, and that a dismissed pair is not re-opened by a later detect run.

**Files:**
- Modify: `backend/app/routers/conflicts.py` (add the PATCH endpoint)
- Test: `backend/tests/test_conflicts_router.py` (append tests)

- [ ] **Step 1: Write the failing tests (append to the test file)**

```python
async def _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch):
    a, b = sorted((rid_a, rid_b))
    monkeypatch.setattr(
        conflicts_mod, "_make_detector",
        lambda: FakeDetector([{"requirement_a": a, "requirement_b": b, "explanation": "Cannot coexist."}]),
    )
    body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
    return body[0]["id"]


@pytest.mark.asyncio
async def test_patch_marks_conflict_resolved(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c8@x.com", "sh_c8@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.patch(f"/conflicts/{cid}", json={"status": "resolved"}, headers=reh)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "resolved"
        # resolved_by is stamped with the engineer's user id
        re_user = await get_db().users.find_one({"email": "re_c8@x.com"})
        doc = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert doc["resolved_by"] == str(re_user["_id"])


@pytest.mark.asyncio
async def test_patch_rejects_invalid_status(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c9@x.com", "sh_c9@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.patch(f"/conflicts/{cid}", json={"status": "open"}, headers=reh)
        assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_patch_on_unowned_conflict_returns_404(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c10@x.com", "sh_c10@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        re2h = await _create_re(c, "re_c10b@x.com")
        r = await c.patch(f"/conflicts/{cid}", json={"status": "dismissed"}, headers=re2h)
        assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_dismissed_conflict_not_reopened_on_redetect(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_c11@x.com", "sh_c11@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        await c.patch(f"/conflicts/{cid}", json={"status": "dismissed"}, headers=reh)
        # Re-run detection — the same pair comes back from the detector
        body = (await c.post(f"/projects/{pid}/conflicts/detect", headers=reh)).json()
        # open list is empty because the only pair stays dismissed
        assert body == []
        doc = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert doc["status"] == "dismissed"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && pytest tests/test_conflicts_router.py -k "patch or reopened" -v`
Expected: FAIL — `405 Method Not Allowed` from missing PATCH route

- [ ] **Step 3: Add the PATCH endpoint**

Append to `backend/app/routers/conflicts.py`:

```python
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
```

- [ ] **Step 4: Run the full router suite to verify it passes**

Run: `cd backend && pytest tests/test_conflicts_router.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Run the whole backend suite to confirm no regressions**

Run: `cd backend && pytest -q`
Expected: PASS (all tests, including pre-existing ones)

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/conflicts.py backend/tests/test_conflicts_router.py
git commit -m "feat: add resolve/dismiss patch endpoint for conflicts"
```

---

### Task 6: Frontend API module

Thin Axios wrapper mirroring `api/requirements.ts`.

**Files:**
- Create: `frontend/src/api/conflicts.ts`

- [ ] **Step 1: Write the module**

```typescript
// frontend/src/api/conflicts.ts
import { api } from "./client";

export type RequirementRef = {
  id: string;
  statement: string;
  stakeholder: string | null;
};

export type Conflict = {
  id: string;
  project_id: string;
  status: "open" | "resolved" | "dismissed";
  explanation: string;
  requirement_a: RequirementRef;
  requirement_b: RequirementRef;
  detected_at: string;
};

export const detectConflicts = (projectId: string) =>
  api.post<Conflict[]>(`/projects/${projectId}/conflicts/detect`).then((r) => r.data);

export const listConflicts = (projectId: string, status?: string) =>
  api
    .get<Conflict[]>(`/projects/${projectId}/conflicts`, { params: status ? { status } : undefined })
    .then((r) => r.data);

export const updateConflict = (id: string, status: "resolved" | "dismissed") =>
  api.patch<Conflict>(`/conflicts/${id}`, { status }).then((r) => r.data);
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/conflicts.ts
git commit -m "feat: add frontend conflicts API module"
```

---

### Task 7: ConflictsPanel component + wire into ProjectDetailPage

Adds the panel (detect button, open-conflict cards with side-by-side requirements + stakeholders + explanation, resolve/dismiss actions, count badge, empty/error states) and mounts it on the project page.

**Files:**
- Create: `frontend/src/components/Conflicts/ConflictsPanel.tsx`
- Modify: `frontend/src/pages/ProjectDetailPage.tsx` (import + render the panel)

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/Conflicts/ConflictsPanel.tsx
import { useCallback, useEffect, useState } from "react";
import {
  detectConflicts,
  listConflicts,
  updateConflict,
  type Conflict,
} from "../../api/conflicts";

export default function ConflictsPanel({ projectId }: { projectId: string }) {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasRun, setHasRun] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const open = await listConflicts(projectId, "open");
      setConflicts(open);
    } catch {
      // a failed background list is non-fatal; keep whatever is shown
    }
  }, [projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function onDetect() {
    setDetecting(true);
    setError(null);
    try {
      const open = await detectConflicts(projectId);
      setConflicts(open);
      setHasRun(true);
    } catch {
      setError("Couldn't run conflict detection. The AI service may be busy — try again.");
    } finally {
      setDetecting(false);
    }
  }

  async function onAct(id: string, status: "resolved" | "dismissed") {
    setActingId(id);
    try {
      await updateConflict(id, status);
      setConflicts((prev) => prev.filter((c) => c.id !== id));
    } finally {
      setActingId(null);
    }
  }

  return (
    <section className="rounded-xl border border-border bg-surface p-4 shadow-card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-foreground">Conflicts</h2>
          {conflicts.length > 0 && (
            <span className="rounded-full bg-accent/10 px-2 py-0.5 text-xs font-semibold text-accent">
              {conflicts.length} open
            </span>
          )}
        </div>
        <button
          onClick={onDetect}
          disabled={detecting}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground shadow-sm transition hover:brightness-110 disabled:opacity-40"
        >
          {detecting ? "Detecting…" : "Detect conflicts"}
        </button>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {conflicts.length === 0 ? (
        <p className="text-sm text-muted py-2 text-center">
          {hasRun ? "No conflicts detected." : "Run detection to check for contradicting requirements."}
        </p>
      ) : (
        <ul className="space-y-3">
          {conflicts.map((c) => (
            <li key={c.id} className="rounded-lg border border-border bg-background p-3 space-y-2">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {[c.requirement_a, c.requirement_b].map((req, i) => (
                  <div key={i} className="rounded-md border border-border bg-surface px-3 py-2">
                    <p className="text-xs font-medium text-accent">{req.stakeholder || "Unknown stakeholder"}</p>
                    <p className="mt-0.5 text-sm text-foreground">{req.statement}</p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted italic">{c.explanation}</p>
              <div className="flex gap-2">
                <button
                  onClick={() => onAct(c.id, "resolved")}
                  disabled={actingId === c.id}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
                >
                  Mark resolved
                </button>
                <button
                  onClick={() => onAct(c.id, "dismissed")}
                  disabled={actingId === c.id}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:bg-surface-muted disabled:opacity-40"
                >
                  Dismiss
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Wire it into `ProjectDetailPage.tsx`**

Add the import after line 14 (`import AppHeader from "../components/AppHeader";`):

```tsx
import ConflictsPanel from "../components/Conflicts/ConflictsPanel";
```

Render the panel inside the content column, immediately before the Sessions `<section>` (before line 176's `{/* Sessions section */}`):

```tsx
          {/* Conflicts section */}
          <ConflictsPanel projectId={id} />
```

- [ ] **Step 3: Verify it type-checks and builds**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: no type errors; build succeeds

- [ ] **Step 4: Manual verification**

Start backend and frontend. As a requirements engineer: open a project that has at least two contradicting requirements from stakeholders, click **Detect conflicts**, confirm a conflict card appears with both statements, stakeholders, and an explanation. Click **Dismiss**; confirm the card disappears and re-running detection does not bring it back. Click **Mark resolved** on another; confirm it disappears.

(No component test is added — this codebase tests stores/services, not React components; this follows the existing pattern.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Conflicts/ConflictsPanel.tsx frontend/src/pages/ProjectDetailPage.tsx
git commit -m "feat: add ConflictsPanel to project page for detect/resolve/dismiss"
```

---

## Notes for the implementer

- **`require_engineer`** (in `backend/app/deps.py`) returns the user doc with `_id` already stringified — `user["_id"]` is the owner id used throughout `projects`/`requirements`.
- **`pair_key` ordering:** `ConflictDetector` always returns `requirement_a <= requirement_b` (sorted ids), so `f"{a}:{b}"` is stable regardless of which order the LLM emitted the pair. The unique index `(project_id, pair_key)` enforces no duplicates at the DB level too.
- **Stakeholder names** come from each session's `stakeholder_id` → `users.real_name`, matching how `sessions.py` resolves names.
- Run `cd backend && pytest -q` and `cd frontend && npx tsc --noEmit` after the final task to confirm the whole thing is green.
