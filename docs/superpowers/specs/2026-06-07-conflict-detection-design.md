# Cross-Stakeholder Conflict Detection — Design

**Date:** 2026-06-07
**Status:** Approved (pending spec review)

## Problem

A project gathers requirements from multiple stakeholders, each interviewed in
their own session. Requirements are extracted per turn and deduplicated *within*
a session ([`backend/app/routers/dialogue.py`](../../../backend/app/routers/dialogue.py)),
then aggregated across sessions for the requirements engineer (SRE) via
`GET /requirements?project_id=` ([`backend/app/routers/requirements.py`](../../../backend/app/routers/requirements.py)).

Nothing detects when requirements from **different stakeholders contradict each
other**. For example, Stakeholder A says "auto-approve refunds" while Stakeholder
B says "all refunds require manager sign-off". Both are stored side by side as
separate `pending` requirements; the SRE must spot the contradiction manually.

Conflicting stakeholder requirements are a well-documented Requirements
Engineering problem (requirements negotiation / viewpoint analysis). Surfacing
them for resolution is a core analyst activity that this tool currently leaves
entirely manual.

## Scope

**In scope:** detect **direct contradictions only** — pairs of requirements that
cannot both be satisfied. High precision is preferred over recall.

**Out of scope (future work):**
- Overlap / near-duplicate detection across stakeholders.
- Ambiguity and terminology-mismatch detection.
- Auto-running detection on session completion (this design is on-demand only).
- A guided "pick a winner / record rationale" resolution workflow (the SRE
  resolves by editing/rejecting requirements through the existing
  `PATCH /requirements/{id}` endpoint).
- Candidate pre-filtering / embeddings for scaling to very large requirement sets.

## Trigger

On-demand. The SRE clicks **"Detect conflicts"** on the project page, which
analyzes all current requirements across the project's stakeholders and stores
the results. Chosen for demo determinism, predictable LLM cost, conceptual
correctness (an analyst activity), and testability.

## Architecture

A new project-level analysis layer over the existing per-session extraction:

1. **Data:** a new `conflicts` MongoDB collection, scoped per project.
2. **Detection:** a `ConflictDetector` service — single-pass Gemini JSON call.
3. **API:** SRE-only detect / list / patch endpoints, ownership-checked.
4. **Frontend:** a Conflicts panel on `ProjectDetailPage`.

### 1. Data model — `conflicts` collection

```
{
  _id,
  project_id:     str,          // owning project
  requirement_a:  str,          // requirement _id
  requirement_b:  str,          // requirement _id
  pair_key:       str,          // sorted(a, b) joined — stable across runs
  explanation:    str,          // LLM's short reason the pair contradicts
  status:         str,          // "open" | "resolved" | "dismissed"
  detected_at:    datetime,
  updated_at:     datetime,
  resolved_by:    str | None,   // SRE user id who resolved/dismissed
}
```

- **`pair_key`** is the two requirement ids sorted and joined. On each detection
  run, a re-found pair that already exists is **not** duplicated; its existing
  `open` / `resolved` / `dismissed` status is preserved. Genuinely new pairs are
  inserted as `open`. This means a **dismissed** false positive stays suppressed,
  and a **resolved** pair does not reappear, on subsequent runs.
- Conflicts store requirement **ids**, not statements, so a conflict always
  reflects the current requirement text and both sides can be rendered live.
- If a referenced requirement has been deleted or rejected since detection, the
  conflict is treated as **stale** and hidden from the open list.

### 2. Detection service — `ConflictDetector`

New file `backend/app/services/conflict_detector.py`, mirroring
`RequirementExtractor`:

```python
class ConflictDetector:
    def __init__(self, *, llm): ...

    async def detect(self, requirements: list[dict]) -> list[dict]:
        # requirements: [{id, statement, stakeholder, type}, ...]
        # returns: [{requirement_a, requirement_b, explanation}, ...]
```

- Each requirement is labelled with its **stakeholder** (resolved from the
  session's `stakeholder_id`) and a short index id, so the LLM can reason across
  stakeholders and reference pairs unambiguously.
- The prompt instructs the model to return **only direct contradictions** — pairs
  that cannot both be satisfied — each with a one-sentence explanation, and
  explicitly **not** to flag mere differences, overlaps, or vagueness. This keeps
  precision high and matches the "contradictions only" scope.
- Uses `temperature=0.2` and `response_mime_type="application/json"`, consistent
  with `RequirementExtractor`.
- The service maps the LLM's index references back to real requirement `_id`s.
  Any malformed or unknown reference is dropped defensively (mirroring the
  extractor's guard for missing fields).

### 3. API — `conflicts.py` router

All endpoints are SRE-only, reusing `_require_sre` and the ownership helpers
(`_owned_session_ids`) from `requirements.py`.

| Endpoint | Purpose |
|---|---|
| `POST /projects/{pid}/conflicts/detect` | Gather all requirements across the project's sessions (excluding `rejected`) → call `ConflictDetector` → upsert results by `pair_key` (preserve existing status, insert new pairs as `open`) → return the current conflict list. |
| `GET /projects/{pid}/conflicts` | List stored conflicts, filterable by status. Each enriched with both requirements' current statements and stakeholder names. Stale conflicts (referencing deleted/rejected requirements) are hidden. |
| `PATCH /conflicts/{id}` | Set status to `resolved` or `dismissed`; stamps `resolved_by` and `updated_at`. |

- On `UpstreamUnavailable` from Gemini, `POST /detect` returns a clean error
  response (consistent with the dialogue routes), not a 500.
- Detection ignores requirements whose status is already `rejected`.

### 4. Frontend surface

Lives on `ProjectDetailPage` (where the SRE already reviews aggregated
requirements) as a new Conflicts panel. No change to the stakeholder-facing flow.

- **New API module** `frontend/src/api/conflicts.ts` mirroring `api/requirements.ts`:
  `detectConflicts(projectId)`, `listConflicts(projectId, status?)`,
  `updateConflict(id, status)`.
- **`ConflictsPanel` component:**
  - A **"Detect conflicts"** button → calls detect, shows a loading state while
    Gemini runs (reuse the `StatusIndicator` / spinner pattern).
  - A list of **open** conflicts. Each card shows the two contradicting
    requirement statements **side by side**, each tagged with its **stakeholder
    name**, plus the LLM's one-line explanation.
  - Per-conflict **Resolve** and **Dismiss** actions → `PATCH /conflicts/{id}`,
    then the card drops out of the open list.
  - A count badge (reuse `ui/Badge.tsx`), e.g. "3 open conflicts".
  - Empty state: "No conflicts detected" after a clean run.
  - Friendly inline error + retry when Gemini is unavailable.

## Testing

Follows existing patterns (`FakeExtractor`, `FakeGen`, fake-LLM injection,
`AsyncClient` integration tests, factory monkeypatching).

**Service unit tests** (`test_conflict_detector.py`) — inject a fake LLM:
- Returns a contradicting pair → mapped to correct requirement ids.
- Returns empty → no conflicts.
- Returns a malformed / unknown index reference → dropped defensively, no crash.
- Prompt includes stakeholder labels.

**Router integration tests** (`test_conflicts_router.py`) — monkeypatch the
detector factory:
- `POST /detect` as SRE → stores conflicts, returns them enriched with statements
  and stakeholder names.
- Idempotent re-run: same pair not duplicated; a **dismissed** pair stays
  dismissed and is not re-opened (the `pair_key` behavior).
- `PATCH /conflicts/{id}` → status transitions; stamps `resolved_by`.
- Auth: non-SRE (stakeholder) → 403; SRE cannot access another owner's project → 404.
- Stale conflict (referenced requirement deleted/rejected) → hidden from open list.
- Gemini `UpstreamUnavailable` → clean error response, not 500.

**Frontend** — a `conflicts` API/store test in the style of `specStore.test.ts`.

## Out-of-scope / future work

- Auto-detection on session completion.
- Overlap, ambiguity, and terminology-mismatch detection.
- Candidate pre-filtering with embeddings to scale to large requirement sets.
- Guided resolution workflow (pick-a-winner, decision rationale, auto-status updates).
