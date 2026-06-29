# Conflict resolution: true Win-Win merge + stakeholder voting — design

**Date:** 2026-06-30
**Status:** Approved, ready for implementation planning
**Scope:** Two linked enhancements to the existing conflict feature, both named as
"future work" in `docs/conflict-resolution-strategy.md`:

1. **Auto-handle counterpart** (Limitation #1 — "single-sided merge"). Today, applying a
   reconciled requirement overwrites only the one side the RE picks; the counterpart lingers at
   `pending`. A true Win-Win replaces *both*.
2. **Stakeholder voting** (Limitation #2 — "no stakeholder-side acceptance"). Stakeholders can
   discuss but cannot signal acceptance of the proposed compromise.

Both stay entirely inside the conflict feature. The requirements engineer (RE) remains the final
decider — voting is **advisory**, not a gate.

## Context — current behaviour

- `ConflictDetector` (`backend/app/services/conflict_detector.py`) flags directly-contradicting
  requirement pairs.
- `POST /projects/{pid}/conflicts/detect` (`backend/app/routers/conflicts.py`) upserts conflicts
  and auto-opens one `conflict_resolution` chat per distinct stakeholder.
- Each chat runs the existing probing flow (`QuestionGenerator` via `POST /sessions/{sid}/turns`
  / `messages`), kept on-topic by the stored conflict summary.
- `POST /conflicts/{cid}/suggest` drafts **one** reconciled statement (`ResolutionSuggester`).
- **The single-sided merge** is in the frontend `onApply` (`ConflictsPanel.tsx`): it calls
  `patchRequirement(reqId, { statement })` then `updateConflict(cid, "resolved")` — and never
  touches the counterpart, which stays `pending` and can be re-flagged on the next detect run and
  can leak into the SRS export.

Relevant facts confirmed in code:

- Requirement statuses (`backend/app/routers/requirements.py`): `pending / approved / rejected /
  needs_clarification`. `rejected` already excludes a requirement from SRS *and* future detection.
- Stakeholder auth: `require_stakeholder` + session ownership (`stakeholder_id == user_id`);
  resolution sessions carry `kind == "conflict_resolution"` and `conflict_id`.
- The frontend `Session` type already exposes `kind` and `conflict_id`, so the stakeholder chat
  already knows which conflict it belongs to.

## End-to-end workflow (target)

0. **Detect** (unchanged) — conflict stored, resolution chat auto-opens per stakeholder.
1. **Explain & discuss** (unchanged) — AI opener + probing `QuestionGenerator`. No vote card yet.
2. **RE proposes** — RE clicks *Suggest* (existing draft), edits, then **Send to stakeholders**
   (`POST /conflicts/{cid}/propose`). This stores the proposal on the conflict and makes the vote
   card appear in each stakeholder chat.
3. **Stakeholders vote** — each chat shows the proposed wording + Accept / Request-changes
   (+ optional comment). Probing chat remains fully usable alongside the card. Votes are advisory.
4. **RE applies** — RE clicks *Apply* (`POST /conflicts/{cid}/apply`): writes the reconciled
   statement onto the chosen surviving requirement, sets the counterpart to `rejected`, and marks
   the conflict `resolved` — one atomic action, no manual cleanup, no re-detection of a settled
   conflict.

## Architectural decisions

- **Auto-handle counterpart → new backend endpoint** `POST /conflicts/{cid}/apply` (not extra
  frontend calls). One atomic, ownership-checked operation; testable; no partial-failure state.
- **Vote storage → on the `conflicts` document** (no new collection). Re-publishing a revised
  proposal clears prior votes.
- **Voting is advisory** — `apply` never checks votes; the RE decides when to apply.

## Data model — `conflicts` collection (new fields)

```
proposal: { statement: str, rationale: str | None, published_at: datetime } | None
votes:    { <stakeholder_id>: { choice: "accept" | "request_changes",
                                comment: str | None, voted_at: datetime } }
```

Defaults: `proposal = None`, `votes = {}`. Existing conflict docs without these fields are read as
the defaults (no migration required).

## API surface

| Endpoint | Auth | Behaviour |
|---|---|---|
| `POST /conflicts/{cid}/propose` | RE owns conflict's project | Body `{ statement, rationale? }`. Sets `proposal` (with `published_at = now`), **clears `votes`**. Returns updated `ConflictOut`. |
| `GET /sessions/{sid}/resolution` | Stakeholder owns session (`kind=conflict_resolution`) | Returns `{ proposal, my_vote }` for the vote card. |
| `POST /sessions/{sid}/vote` | Stakeholder owns session (`kind=conflict_resolution`) | Body `{ choice, comment? }`. Validates `choice ∈ {accept, request_changes}`; records/overwrites `conflicts.votes[stakeholder_id]`. 409 if session has no proposal yet; 422 on bad choice. |
| `POST /conflicts/{cid}/apply` | RE owns conflict's project | Body `{ surviving_requirement_id, statement }`. `surviving_requirement_id` must be one of the conflict's two requirements; the other is the counterpart. Writes `statement` onto surviving, sets counterpart `status=rejected`, sets conflict `status=resolved` (+ `resolved_by`). 404 on stale/removed requirement; 422 if id is not part of the conflict. |

`ConflictOut` (and `conflicts.ts` type) gain:

- `proposal: { statement, rationale, published_at } | null`
- `votes: [{ stakeholder: str | None, choice, comment, voted_at }]` — resolved to stakeholder
  names via a `uid → real_name` lookup (mirrors the existing `_project_session_names` enrichment).

## Frontend

**RE panel — `ConflictsPanel.tsx`:**
- After *Suggest*, add a **Send to stakeholders** button → `propose(cid, statement, rationale)`.
- Render per-stakeholder vote status from `conflict.votes` (e.g. "Sales: accepted", "Finance:
  requested changes — '…'"), plus a summary count.
- Repoint the existing *Apply to <stakeholder>'s statement* buttons at `apply(cid,
  survivingId, statement)` (single call), replacing the two-call `patchRequirement` +
  `updateConflict` sequence in `onApply`.

**Stakeholder chat — `ChatPanel.tsx` (+ chat page wiring):**
- When `session.kind === "conflict_resolution"`, fetch `GET /sessions/{sid}/resolution`.
- If a `proposal` exists, render a **vote card** above the input: proposed wording, Accept /
  Request-changes buttons, optional comment field; reflects `my_vote` if already cast; calls
  `POST /sessions/{sid}/vote`. The probing chat is untouched.

**API client — `frontend/src/api/conflicts.ts` / `sessions.ts`:** add `propose`, `applyResolution`,
`getResolution`, `voteResolution`; extend the `Conflict` type with `proposal` + `votes`.

## Error handling & edge cases

- **Stale requirement** in `apply` → 404 "conflict references a removed requirement" (mirror the
  existing guard in `suggest_resolution`).
- **Same-stakeholder conflict** → one resolution session, one vote; `apply` still picks a surviving
  side and rejects the counterpart. No special-casing.
- **Re-publish** a revised proposal → `votes` cleared so stakeholders vote on the current wording.
- **Vote before proposal exists** → 409 (the card only renders when a proposal is present, but the
  endpoint guards independently).
- **Idempotent re-vote** → a stakeholder voting again overwrites their prior choice.

## Testing

**Backend** (extend `test_conflicts_router.py`, `test_conflict_resolution.py`):
- `apply`: writes statement to surviving, sets counterpart `rejected`, conflict `resolved`;
  ownership (404 for non-owner); `surviving_requirement_id` not in conflict → 422; stale req → 404.
- `propose`: stores proposal, clears existing votes, ownership-checked.
- `vote`: records and overwrites; rejects non-`conflict_resolution` sessions and non-owners; 409
  when no proposal; 422 on bad choice.
- `ConflictOut`: surfaces `proposal` + `votes` with stakeholder names.

**Frontend** (mirror existing `conflictMap.test.ts` / `contactMessage.test.ts` patterns):
- Vote-status rendering from `conflict.votes`.
- *Apply* invokes the new single endpoint.

## Out of scope (unchanged future work)

- Hard-gate voting (Option 2), MoSCoW prioritization ceremony, and per-requirement → business-goal
  RTM trace remain future work per `docs/conflict-resolution-strategy.md`.
