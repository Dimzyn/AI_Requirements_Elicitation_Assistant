# Conflict Win-Win Merge + Stakeholder Voting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make conflict resolution close *both* sides of a conflict in one action, and let stakeholders vote (advisory) on the RE's proposed compromise.

**Architecture:** A new atomic `POST /conflicts/{cid}/apply` writes the reconciled statement onto the surviving requirement, rejects the counterpart, and resolves the conflict. A published `proposal` plus per-stakeholder `votes` are stored on the `conflicts` document; the RE publishes via `POST /conflicts/{cid}/propose`, stakeholders read/cast via `GET|POST /sessions/{sid}/resolution|vote`, and the RE sees vote status on the conflicts panel.

**Tech Stack:** FastAPI + Motor (async MongoDB), Pydantic v2; React + TypeScript + Zustand + Tailwind; pytest (httpx ASGITransport) and vitest.

## Global Constraints

- Voting is **advisory** — `apply` MUST NOT check votes; the RE is the final decider.
- Requirement statuses are exactly `pending / approved / rejected / needs_clarification`; the counterpart is retired with `rejected` (already excluded from SRS + detection).
- Conflict statuses exposed to clients stay `open / resolved / dismissed`.
- New conflict fields default to `proposal = None`, `votes = {}`; existing docs without them read as the defaults (no migration).
- Stakeholder-facing endpoints use `require_stakeholder` + session ownership (`stakeholder_id == user_id`) and only act on sessions with `kind == "conflict_resolution"`.
- Backend tests run from the `backend/` directory (imports are `from app...` / `from tests.helpers...`).
- Vote choices are exactly `accept` / `request_changes`.

---

### Task 1: Backend — atomic `apply` endpoint (closes the single-sided merge)

**Files:**
- Modify: `backend/app/schemas/conflict.py` (add `ApplyIn`, `ApplyOut`)
- Modify: `backend/app/routers/conflicts.py` (add `apply_resolution` endpoint + imports)
- Test: `backend/tests/test_conflicts_router.py` (append tests; reuses `_setup_project_with_two_reqs`, `_detect_one`, `_create_re`)

**Interfaces:**
- Consumes: existing `_project_session_names(db, owner_id, project_id)`, `require_engineer`.
- Produces: `POST /conflicts/{cid}/apply` body `{ surviving_requirement_id: str, statement: str }` → `{ id: str, status: str }`. Side effects: surviving requirement's `statement` updated; counterpart `status="rejected"`; conflict `status="resolved"`, `resolved_by=<re id>`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_conflicts_router.py`:

```python
@pytest.mark.asyncio
async def test_apply_writes_surviving_rejects_counterpart_resolves(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_ap1@x.com", "sh_ap1@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.post(
            f"/conflicts/{cid}/apply",
            json={
                "surviving_requirement_id": rid_a,
                "statement": "Refunds under $50 auto-approve; $50+ need sign-off.",
            },
            headers=reh,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "resolved"
        surv = await get_db().requirements.find_one({"_id": ObjectId(rid_a)})
        ctr = await get_db().requirements.find_one({"_id": ObjectId(rid_b)})
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert surv["statement"].startswith("Refunds under $50")
        assert ctr["status"] == "rejected"
        assert conf["status"] == "resolved"


@pytest.mark.asyncio
async def test_apply_rejects_surviving_id_not_in_conflict(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_ap2@x.com", "sh_ap2@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        r = await c.post(
            f"/conflicts/{cid}/apply",
            json={"surviving_requirement_id": str(ObjectId()), "statement": "X."},
            headers=reh,
        )
        assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_apply_on_unowned_conflict_returns_404(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, pid, sid, (rid_a, rid_b) = await _setup_project_with_two_reqs(
            c, "re_ap3@x.com", "sh_ap3@x.com"
        )
        cid = await _detect_one(c, reh, pid, rid_a, rid_b, monkeypatch)
        re2h = await _create_re(c, "re_ap3b@x.com")
        r = await c.post(
            f"/conflicts/{cid}/apply",
            json={"surviving_requirement_id": rid_a, "statement": "X."},
            headers=re2h,
        )
        assert r.status_code == 404, r.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_conflicts_router.py -k apply -v`
Expected: FAIL — `404 Not Found` (route does not exist yet).

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/conflict.py`, append:

```python
class ApplyIn(BaseModel):
    surviving_requirement_id: str
    statement: str


class ApplyOut(BaseModel):
    id: str
    status: str
```

- [ ] **Step 4: Implement the endpoint**

In `backend/app/routers/conflicts.py`, extend the schema import to include the new names:

```python
from ..schemas.conflict import (
    ApplyIn,
    ApplyOut,
    ConflictOut,
    ConflictPatch,
    RequirementRef,
    ResolutionSessionRef,
    ResolutionSuggestion,
)
```

Then append this endpoint at the end of the file:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_conflicts_router.py -k apply -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/conflict.py backend/app/routers/conflicts.py backend/tests/test_conflicts_router.py
git commit -m "feat: atomic apply endpoint that retires the conflict counterpart"
```

---

### Task 2: Backend — `propose` endpoint + surface `proposal`/`votes` on `ConflictOut`

**Files:**
- Modify: `backend/app/schemas/conflict.py` (add `ProposalOut`, `VoteOut`, `ProposeIn`; extend `ConflictOut`)
- Modify: `backend/app/routers/conflicts.py` (add `_uid_to_name`, enrich `_conflict_to_out`, add `propose_resolution`)
- Test: `backend/tests/test_conflict_resolution.py` (append; reuses `_detect_one_conflict`, `_create_re`, `_add_stakeholder`)

**Interfaces:**
- Consumes: `_conflict_to_out`, `_project_session_names`, `require_engineer`.
- Produces:
  - `ConflictOut.proposal: ProposalOut | None` and `ConflictOut.votes: list[VoteOut]`.
  - `POST /conflicts/{cid}/propose` body `{ statement: str, rationale: str | None }` → `ConflictOut`. Side effect: sets `proposal = {statement, rationale, published_at}`, clears `votes` to `{}`.
  - Helper `_uid_to_name(db, uid) -> str | None`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_conflict_resolution.py`:

```python
@pytest.mark.asyncio
async def test_propose_sets_proposal_and_surfaces_on_list(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_prop1@x.com", sh_email="sh_prop1@x.com"
        )
        r = await c.post(
            f"/conflicts/{cid}/propose",
            json={"statement": "Compromise wording.", "rationale": "Splits the difference."},
            headers=reh,
        )
        assert r.status_code == 200, r.text
        assert r.json()["proposal"]["statement"] == "Compromise wording."
        assert r.json()["votes"] == []
        listed = (await c.get(f"/projects/{pid}/conflicts", headers=reh)).json()
        assert listed[0]["proposal"]["statement"] == "Compromise wording."


@pytest.mark.asyncio
async def test_propose_clears_existing_votes(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_prop2@x.com", sh_email="sh_prop2@x.com"
        )
        sh_user = await get_db().users.find_one({"email": "sh_prop2@x.com"})
        # seed a stale vote directly, then re-propose
        await get_db().conflicts.update_one(
            {"_id": ObjectId(cid)},
            {"$set": {f"votes.{str(sh_user['_id'])}": {"choice": "accept", "comment": None, "voted_at": datetime.now(timezone.utc)}}},
        )
        await c.post(f"/conflicts/{cid}/propose", json={"statement": "New wording."}, headers=reh)
        conf = await get_db().conflicts.find_one({"_id": ObjectId(cid)})
        assert conf.get("votes", {}) == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_conflict_resolution.py -k propose -v`
Expected: FAIL — `404 Not Found` (route missing).

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/conflict.py`, add the two output models and the input, and extend `ConflictOut`:

```python
class ProposalOut(BaseModel):
    statement: str
    rationale: str | None = None
    published_at: datetime


class VoteOut(BaseModel):
    stakeholder: str | None = None
    choice: str
    comment: str | None = None
    voted_at: datetime


class ProposeIn(BaseModel):
    statement: str
    rationale: str | None = None
```

Add these two fields to `ConflictOut` (after `resolution_sessions`):

```python
    proposal: ProposalOut | None = None
    votes: list[VoteOut] = []
```

- [ ] **Step 4: Enrich `_conflict_to_out` and add the endpoint**

In `backend/app/routers/conflicts.py`, add `ProposalOut`, `VoteOut`, `ProposeIn` to the schema import block.

Add this helper near the other helpers (e.g. after `_req_ref`):

```python
async def _uid_to_name(db, uid: str | None) -> str | None:
    """Resolve a stakeholder user id to their real name (None if missing/invalid)."""
    if not uid:
        return None
    try:
        u = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        return None
    return (u or {}).get("real_name")
```

In `_conflict_to_out`, build the proposal + votes and pass them to `ConflictOut(...)`. Replace the existing `return ConflictOut(...)` block with:

```python
    prop = doc.get("proposal")
    votes_out: list[VoteOut] = []
    for uid, v in (doc.get("votes") or {}).items():
        votes_out.append(
            VoteOut(
                stakeholder=await _uid_to_name(db, uid),
                choice=v.get("choice"),
                comment=v.get("comment"),
                voted_at=v.get("voted_at"),
            )
        )
    return ConflictOut(
        id=str(doc["_id"]),
        project_id=doc["project_id"],
        status=doc.get("status", "open"),
        explanation=doc.get("explanation", ""),
        requirement_a=ref_a,
        requirement_b=ref_b,
        resolution_sessions=await _resolution_refs(db, str(doc["_id"]), session_names),
        proposal=ProposalOut(**prop) if prop else None,
        votes=votes_out,
        detected_at=doc["detected_at"],
    )
```

Append the endpoint at the end of the file:

```python
@router.post("/conflicts/{cid}/propose", response_model=ConflictOut)
async def propose_resolution(cid: str, body: ProposeIn, user: dict = Depends(require_engineer)):
    """Publish the (RE-edited) reconciled wording to the conflict so stakeholders can
    vote on it. Re-publishing clears prior votes."""
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

    statement = (body.statement or "").strip()
    if not statement:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "statement is required")

    now = datetime.now(timezone.utc)
    doc = await db.conflicts.find_one_and_update(
        {"_id": oid},
        {"$set": {
            "proposal": {"statement": statement, "rationale": body.rationale or None, "published_at": now},
            "votes": {},
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    out = await _conflict_to_out(db, doc, session_names)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict references a removed requirement")
    return out
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_conflict_resolution.py -k propose -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full conflict test files to confirm no regression**

Run: `cd backend && python -m pytest tests/test_conflicts_router.py tests/test_conflict_resolution.py -v`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/conflict.py backend/app/routers/conflicts.py backend/tests/test_conflict_resolution.py
git commit -m "feat: publish a reconciled proposal and surface proposal+votes on conflicts"
```

---

### Task 3: Backend — stakeholder `vote` + `resolution` card endpoints

**Files:**
- Modify: `backend/app/schemas/conflict.py` (add `VoteIn`, `ResolutionCardOut`)
- Modify: `backend/app/routers/conflicts.py` (import `require_stakeholder`; add `_VALID_VOTE_CHOICES`, `vote_resolution`, `get_resolution_card`)
- Test: `backend/tests/test_conflict_resolution.py` (append)

**Interfaces:**
- Consumes: `ProposalOut`, `VoteOut` (Task 2), `require_stakeholder`.
- Produces:
  - `POST /sessions/{sid}/vote` body `{ choice: "accept"|"request_changes", comment: str | None }` → `ResolutionCardOut`. Records `conflicts.votes[<stakeholder_id>]`. 409 if no proposal; 422 on bad choice; 404 if session not owned / not a resolution session.
  - `GET /sessions/{sid}/resolution` → `ResolutionCardOut { proposal, my_vote }`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_conflict_resolution.py`:

```python
async def _resolution_sid(cid):
    rs = await get_db().sessions.find_one({"conflict_id": cid, "kind": "conflict_resolution"})
    return str(rs["_id"])


@pytest.mark.asyncio
async def test_vote_flow_records_and_surfaces(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_v1@x.com", sh_email="sh_v1@x.com"
        )
        rsid = await _resolution_sid(cid)
        # voting before a proposal exists is a 409
        pre = await c.post(f"/sessions/{rsid}/vote", json={"choice": "accept"}, headers=sh)
        assert pre.status_code == 409, pre.text
        # RE proposes, then the stakeholder accepts
        await c.post(f"/conflicts/{cid}/propose", json={"statement": "Compromise wording."}, headers=reh)
        r = await c.post(f"/sessions/{rsid}/vote", json={"choice": "accept"}, headers=sh)
        assert r.status_code == 200, r.text
        assert r.json()["my_vote"]["choice"] == "accept"
        # the RE's conflict list now shows the vote with the stakeholder name
        listed = (await c.get(f"/projects/{pid}/conflicts", headers=reh)).json()
        assert listed[0]["votes"][0]["choice"] == "accept"
        assert listed[0]["votes"][0]["stakeholder"] == "Alice"
        # the resolution card echoes proposal + my_vote
        card = (await c.get(f"/sessions/{rsid}/resolution", headers=sh)).json()
        assert card["proposal"]["statement"] == "Compromise wording."
        assert card["my_vote"]["choice"] == "accept"


@pytest.mark.asyncio
async def test_vote_overwrites_and_validates_choice(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid, cid, _, _ = await _detect_one_conflict(
            c, monkeypatch, re_email="re_v2@x.com", sh_email="sh_v2@x.com"
        )
        rsid = await _resolution_sid(cid)
        await c.post(f"/conflicts/{cid}/propose", json={"statement": "W."}, headers=reh)
        await c.post(f"/sessions/{rsid}/vote", json={"choice": "accept"}, headers=sh)
        # overwrite with request_changes
        await c.post(
            f"/sessions/{rsid}/vote",
            json={"choice": "request_changes", "comment": "Too strict."},
            headers=sh,
        )
        card = (await c.get(f"/sessions/{rsid}/resolution", headers=sh)).json()
        assert card["my_vote"]["choice"] == "request_changes"
        assert card["my_vote"]["comment"] == "Too strict."
        # bad choice rejected
        bad = await c.post(f"/sessions/{rsid}/vote", json={"choice": "maybe"}, headers=sh)
        assert bad.status_code == 422, bad.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd backend && python -m pytest tests/test_conflict_resolution.py -k vote -v`
Expected: FAIL — `404 Not Found` (routes missing).

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/conflict.py`, append:

```python
class VoteIn(BaseModel):
    choice: str
    comment: str | None = None


class ResolutionCardOut(BaseModel):
    proposal: ProposalOut | None = None
    my_vote: VoteOut | None = None
```

- [ ] **Step 4: Implement the two endpoints**

In `backend/app/routers/conflicts.py`:

Update the deps import to add `require_stakeholder`:

```python
from ..deps import require_engineer, require_stakeholder
```

Add `ResolutionCardOut` and `VoteIn` to the schema import block.

Add the choices constant next to `_VALID_CONFLICT_STATUSES`:

```python
_VALID_VOTE_CHOICES = {"accept", "request_changes"}
```

Add a small session-lookup helper near the other helpers:

```python
async def _owned_resolution_session(db, sid: str, user_id: str) -> dict | None:
    """The stakeholder's own conflict-resolution session, or None."""
    try:
        oid = ObjectId(sid)
    except Exception:
        return None
    return await db.sessions.find_one(
        {"_id": oid, "stakeholder_id": user_id, "kind": "conflict_resolution"}
    )
```

Append both endpoints at the end of the file:

```python
@router.post("/sessions/{sid}/vote", response_model=ResolutionCardOut)
async def vote_resolution(sid: str, body: VoteIn, user: dict = Depends(require_stakeholder)):
    """Record this stakeholder's advisory vote on the conflict's current proposal."""
    db = get_db()
    session = await _owned_resolution_session(db, sid, user["_id"])
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    if body.choice not in _VALID_VOTE_CHOICES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"choice must be one of {_VALID_VOTE_CHOICES}",
        )
    try:
        conflict = await db.conflicts.find_one({"_id": ObjectId(session["conflict_id"])})
    except Exception:
        conflict = None
    if not conflict:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")
    proposal = conflict.get("proposal")
    if not proposal:
        raise HTTPException(status.HTTP_409_CONFLICT, "no proposal to vote on yet")

    now = datetime.now(timezone.utc)
    vote = {"choice": body.choice, "comment": body.comment or None, "voted_at": now}
    await db.conflicts.update_one(
        {"_id": conflict["_id"]},
        {"$set": {f"votes.{user['_id']}": vote, "updated_at": now}},
    )
    return ResolutionCardOut(
        proposal=ProposalOut(**proposal),
        my_vote=VoteOut(stakeholder=None, **vote),
    )


@router.get("/sessions/{sid}/resolution", response_model=ResolutionCardOut)
async def get_resolution_card(sid: str, user: dict = Depends(require_stakeholder)):
    """Proposal + this stakeholder's current vote, for rendering the in-chat vote card."""
    db = get_db()
    session = await _owned_resolution_session(db, sid, user["_id"])
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    try:
        conflict = await db.conflicts.find_one({"_id": ObjectId(session["conflict_id"])})
    except Exception:
        conflict = None
    if not conflict:
        return ResolutionCardOut()
    proposal = conflict.get("proposal")
    mine = (conflict.get("votes") or {}).get(user["_id"])
    return ResolutionCardOut(
        proposal=ProposalOut(**proposal) if proposal else None,
        my_vote=VoteOut(stakeholder=None, **mine) if mine else None,
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && python -m pytest tests/test_conflict_resolution.py -k vote -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run all conflict backend tests**

Run: `cd backend && python -m pytest tests/test_conflicts_router.py tests/test_conflict_resolution.py -v`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/conflict.py backend/app/routers/conflicts.py backend/tests/test_conflict_resolution.py
git commit -m "feat: stakeholder vote + resolution-card endpoints for conflict proposals"
```

---

### Task 4: Frontend — API client, `Conflict` type, and `voteSummary` helper

**Files:**
- Modify: `frontend/src/api/conflicts.ts` (extend `Conflict`; add types + 4 functions)
- Create: `frontend/src/components/Conflicts/voteSummary.ts`
- Test: `frontend/src/components/Conflicts/voteSummary.test.ts`

**Interfaces:**
- Produces (consumed by Tasks 5 & 6):
  - Types `ResolutionProposal`, `ResolutionVote`, `ResolutionCard`; `Conflict.proposal: ResolutionProposal | null`, `Conflict.votes: ResolutionVote[]`.
  - `proposeResolution(cid, statement, rationale?) => Promise<Conflict>`
  - `applyResolution(cid, survivingRequirementId, statement) => Promise<{ id: string; status: string }>`
  - `getResolutionCard(sessionId) => Promise<ResolutionCard>`
  - `voteResolution(sessionId, choice, comment?) => Promise<ResolutionCard>`
  - `voteSummary(votes: ResolutionVote[]) => string`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/Conflicts/voteSummary.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { voteSummary } from "./voteSummary";
import type { ResolutionVote } from "../../api/conflicts";

const vote = (choice: ResolutionVote["choice"]): ResolutionVote => ({
  stakeholder: "Alice",
  choice,
  comment: null,
  voted_at: "2026-01-01T00:00:00Z",
});

describe("voteSummary", () => {
  it("returns 'No votes yet' when empty", () => {
    expect(voteSummary([])).toBe("No votes yet");
  });

  it("counts accepts and change requests", () => {
    expect(voteSummary([vote("accept"), vote("request_changes")])).toBe(
      "1 accepted, 1 requested changes"
    );
  });

  it("omits a zero bucket", () => {
    expect(voteSummary([vote("accept"), vote("accept")])).toBe("2 accepted");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/Conflicts/voteSummary.test.ts`
Expected: FAIL — cannot resolve `./voteSummary` (and `ResolutionVote` export).

- [ ] **Step 3: Extend the API client**

In `frontend/src/api/conflicts.ts`, add the new types and extend `Conflict`:

```ts
export type ResolutionProposal = {
  statement: string;
  rationale: string | null;
  published_at: string;
};

export type ResolutionVote = {
  stakeholder: string | null;
  choice: "accept" | "request_changes";
  comment: string | null;
  voted_at: string;
};
```

Add these two fields to the `Conflict` type (after `resolution_sessions`):

```ts
  proposal: ResolutionProposal | null;
  votes: ResolutionVote[];
```

Append the new functions and card type:

```ts
export const proposeResolution = (cid: string, statement: string, rationale?: string | null) =>
  api.post<Conflict>(`/conflicts/${cid}/propose`, { statement, rationale }).then((r) => r.data);

export const applyResolution = (
  cid: string,
  survivingRequirementId: string,
  statement: string
) =>
  api
    .post<{ id: string; status: string }>(`/conflicts/${cid}/apply`, {
      surviving_requirement_id: survivingRequirementId,
      statement,
    })
    .then((r) => r.data);

export type ResolutionCard = {
  proposal: ResolutionProposal | null;
  my_vote: ResolutionVote | null;
};

export const getResolutionCard = (sessionId: string) =>
  api.get<ResolutionCard>(`/sessions/${sessionId}/resolution`).then((r) => r.data);

export const voteResolution = (
  sessionId: string,
  choice: "accept" | "request_changes",
  comment?: string
) =>
  api
    .post<ResolutionCard>(`/sessions/${sessionId}/vote`, { choice, comment })
    .then((r) => r.data);
```

- [ ] **Step 4: Write the helper**

Create `frontend/src/components/Conflicts/voteSummary.ts`:

```ts
import type { ResolutionVote } from "../../api/conflicts";

export function voteSummary(votes: ResolutionVote[]): string {
  if (votes.length === 0) return "No votes yet";
  const accepted = votes.filter((v) => v.choice === "accept").length;
  const changes = votes.filter((v) => v.choice === "request_changes").length;
  const parts: string[] = [];
  if (accepted) parts.push(`${accepted} accepted`);
  if (changes) parts.push(`${changes} requested changes`);
  return parts.join(", ");
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/Conflicts/voteSummary.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 6: Typecheck (the `Conflict` type change must not break existing files)**

Run: `cd frontend && npm run build`
Expected: build succeeds. If `conflictMap.test.ts`'s inline `Conflict` fixture errors on the new required fields, add `proposal: null, votes: []` to that fixture object in `frontend/src/components/Conflicts/conflictMap.test.ts`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/conflicts.ts frontend/src/components/Conflicts/voteSummary.ts frontend/src/components/Conflicts/voteSummary.test.ts frontend/src/components/Conflicts/conflictMap.test.ts
git commit -m "feat: conflict resolution API client (propose/apply/vote) + voteSummary helper"
```

---

### Task 5: Frontend — RE panel: Send-to-stakeholders, vote status, repointed Apply

**Files:**
- Modify: `frontend/src/components/Conflicts/ConflictsPanel.tsx`

**Interfaces:**
- Consumes: `proposeResolution`, `applyResolution` (Task 4), `voteSummary` (Task 4), `Conflict.proposal`, `Conflict.votes`.
- Produces: no new exports (UI wiring only).

- [ ] **Step 1: Swap imports**

In `frontend/src/components/Conflicts/ConflictsPanel.tsx`, change the api imports. Replace:

```ts
import {
  detectConflicts,
  listConflicts,
  updateConflict,
  suggestResolution,
  type Conflict,
} from "../../api/conflicts";
import { patchRequirement } from "../../api/requirements";
```

with:

```ts
import {
  detectConflicts,
  listConflicts,
  updateConflict,
  suggestResolution,
  proposeResolution,
  applyResolution,
  type Conflict,
} from "../../api/conflicts";
import { voteSummary } from "./voteSummary";
```

(`patchRequirement` is no longer used in this file.)

- [ ] **Step 2: Add proposing state**

Below `const [applyingKey, setApplyingKey] = useState<string | null>(null);` add:

```ts
  const [proposingId, setProposingId] = useState<string | null>(null);
```

- [ ] **Step 3: Repoint `onApply` at the atomic endpoint**

Replace the body of `onApply` (the `patchRequirement` + `updateConflict` pair) with a single call:

```ts
  async function onApply(c: Conflict, requirementId: string) {
    const draft = suggestState[c.id]?.suggestion?.trim();
    if (!draft) return;
    const key = `${c.id}-${requirementId}`;
    setApplyingKey(key);
    try {
      await applyResolution(c.id, requirementId, draft);
      setConflicts((prev) => prev.filter((x) => x.id !== c.id));
      setExpandedId((prev) => (prev === c.id ? null : prev));
      setSuggestState((prev) => {
        const next = { ...prev };
        delete next[c.id];
        return next;
      });
    } finally {
      setApplyingKey(null);
    }
  }
```

- [ ] **Step 4: Add `onPropose`**

Add this function next to `onApply`:

```ts
  // Publish the (edited) reconciled wording to the stakeholders' chats for voting.
  async function onPropose(c: Conflict) {
    const draft = suggestState[c.id]?.suggestion?.trim();
    if (!draft) return;
    setProposingId(c.id);
    try {
      const updated = await proposeResolution(c.id, draft, suggestState[c.id]?.rationale ?? null);
      setConflicts((prev) => prev.map((x) => (x.id === c.id ? updated : x)));
    } finally {
      setProposingId(null);
    }
  }
```

- [ ] **Step 5: Render proposal + vote status**

Directly after the `c.resolution_sessions.length > 0 && (...)` block (before the `<div className="flex gap-2">` action row), insert:

```tsx
              {c.proposal && (
                <div className="rounded-md border border-dashed border-border bg-surface px-2 py-1.5 text-xs space-y-1">
                  <p className="text-muted">
                    Sent to stakeholders:{" "}
                    <span className="text-foreground">{c.proposal.statement}</span>
                  </p>
                  <p className="text-muted">{voteSummary(c.votes)}</p>
                  {c.votes.map((v, i) => (
                    <p key={i} className="text-foreground">
                      {v.stakeholder ?? "Stakeholder"}:{" "}
                      {v.choice === "accept" ? "accepted" : "requested changes"}
                      {v.comment ? ` — “${v.comment}”` : ""}
                    </p>
                  ))}
                </div>
              )}
```

- [ ] **Step 6: Add the "Send to stakeholders" button**

In the suggestion block, inside the `<div className="flex flex-wrap items-center gap-2">` that holds the "Apply to:" buttons, add a Send button as the first child (before the `<span>Apply to:</span>`):

```tsx
                          <button
                            onClick={() => onPropose(c)}
                            disabled={proposingId === c.id || !ss.suggestion?.trim()}
                            className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground transition hover:brightness-110 disabled:opacity-40"
                          >
                            {proposingId === c.id ? "Sending…" : "Send to stakeholders"}
                          </button>
```

- [ ] **Step 7: Typecheck / build**

Run: `cd frontend && npm run build`
Expected: build succeeds with no unused-import or type errors.

- [ ] **Step 8: Manual verification**

Start the app, open a project with a detected conflict as the RE: click *Suggest*, edit, click *Send to stakeholders* → the "Sent to stakeholders" line + "No votes yet" appears; clicking an *Apply to <stakeholder>* button removes the conflict from the open list, and (verify in DB or the requirements view) the counterpart is now `rejected`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/Conflicts/ConflictsPanel.tsx
git commit -m "feat: RE panel sends proposals, shows vote status, applies via atomic endpoint"
```

---

### Task 6: Frontend — in-chat stakeholder vote card

**Files:**
- Create: `frontend/src/components/Dialogue/ResolutionVoteCard.tsx`
- Modify: `frontend/src/pages/MainPage.tsx` (mount the card in the stakeholder branch)

**Interfaces:**
- Consumes: `getResolutionCard`, `voteResolution`, `ResolutionCard` (Task 4).
- Produces: default-exported `ResolutionVoteCard({ sessionId }: { sessionId: string })`. Self-hides (renders `null`) when the session is not a resolution session or has no published proposal.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Dialogue/ResolutionVoteCard.tsx`:

```tsx
import { useEffect, useState } from "react";
import { getResolutionCard, voteResolution, type ResolutionCard } from "../../api/conflicts";

// Self-contained: fetches the conflict proposal for this resolution session and
// renders the Accept / Request-changes card. Renders nothing for normal interview
// sessions (the endpoint 404s) or before the RE has published a proposal.
export default function ResolutionVoteCard({ sessionId }: { sessionId: string }) {
  const [card, setCard] = useState<ResolutionCard | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    setCard(null);
    getResolutionCard(sessionId)
      .then((c) => {
        if (alive) setCard(c);
      })
      .catch(() => {
        if (alive) setCard(null);
      });
    return () => {
      alive = false;
    };
  }, [sessionId]);

  if (!card || !card.proposal) return null;

  async function vote(choice: "accept" | "request_changes") {
    setBusy(true);
    try {
      const updated = await voteResolution(sessionId, choice, comment || undefined);
      setCard(updated);
    } finally {
      setBusy(false);
    }
  }

  const myChoice = card.my_vote?.choice;
  return (
    <div className="mx-6 mb-3 rounded-xl border border-border bg-surface p-3 shadow-card space-y-2">
      <p className="text-xs font-medium text-accent">Proposed resolution — do you accept?</p>
      <p className="text-sm text-foreground">{card.proposal.statement}</p>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Optional: what would you change?"
        rows={2}
        className="w-full resize-none rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground"
      />
      <div className="flex items-center gap-2">
        <button
          onClick={() => vote("accept")}
          disabled={busy}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-foreground transition hover:brightness-110 disabled:opacity-40"
        >
          {myChoice === "accept" ? "Accepted ✓" : "Accept"}
        </button>
        <button
          onClick={() => vote("request_changes")}
          disabled={busy}
          className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
        >
          {myChoice === "request_changes" ? "Changes requested ✓" : "Request changes"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Mount it in the stakeholder chat**

In `frontend/src/pages/MainPage.tsx`, add the import:

```tsx
import ResolutionVoteCard from "../components/Dialogue/ResolutionVoteCard";
```

In the stakeholder (non-RE) branch, render the card between `<ChatPanel />` and `<InputBox />`:

```tsx
          <main className="flex flex-col overflow-hidden bg-surface-muted">
            <ChatPanel />
            {activeId && <ResolutionVoteCard sessionId={activeId} />}
            <InputBox />
          </main>
```

- [ ] **Step 3: Typecheck / build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual verification (end-to-end)**

As the RE, *Send to stakeholders* on a conflict. Log in as the stakeholder, open the "Resolve requirement conflict" chat → the vote card shows the proposed wording; the probing chat above is unchanged and still usable. Click *Accept* → button shows "Accepted ✓". Back as the RE, refresh the conflicts panel → vote status shows "1 accepted" (and the stakeholder's name). Click *Apply* → conflict clears and the counterpart is `rejected`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Dialogue/ResolutionVoteCard.tsx frontend/src/pages/MainPage.tsx
git commit -m "feat: in-chat stakeholder vote card for conflict proposals"
```

---

## Self-Review

**Spec coverage:**
- Auto-handle counterpart (single-sided merge) → Task 1 (`apply` rejects counterpart + resolves). ✅
- `proposal` + `votes` data model → Tasks 2 & 3. ✅
- `POST /conflicts/{cid}/propose` → Task 2. ✅
- `POST /sessions/{sid}/vote`, `GET /sessions/{sid}/resolution` → Task 3. ✅
- `POST /conflicts/{cid}/apply` → Task 1. ✅
- `ConflictOut` extended with proposal + named votes → Task 2. ✅
- RE panel: Send-to-stakeholders, vote status, repointed Apply → Task 5. ✅
- Stakeholder in-chat vote card, probing untouched → Task 6. ✅
- Advisory (no gate in `apply`) → Task 1 (no vote check). ✅
- Edge cases: stale requirement (Task 1 404), surviving-id-not-in-conflict (Task 1 422), same-stakeholder (works unchanged — single resolution session, single vote), re-publish clears votes (Task 2), vote-before-proposal 409 + bad-choice 422 + overwrite (Task 3). ✅
- Tests: backend extends both conflict test files; frontend adds `voteSummary` vitest + build typecheck. ✅

**Placeholder scan:** No TBD/TODO; every code step shows complete code; every command has expected output.

**Type consistency:** `proposeResolution / applyResolution / getResolutionCard / voteResolution` and `voteSummary` are defined in Task 4 and consumed with matching signatures in Tasks 5–6. Backend `ProposalOut / VoteOut / ResolutionCardOut / ApplyOut / ApplyIn / ProposeIn / VoteIn` defined before use. `_owned_resolution_session`, `_uid_to_name` defined in the tasks that add them. `ResolutionCard.my_vote` / `proposal` names match between backend response model and frontend type.

## Out of scope (unchanged future work)
Hard-gate voting, MoSCoW prioritization ceremony, and per-requirement → business-goal RTM trace remain future work per `docs/conflict-resolution-strategy.md`.
