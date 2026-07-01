# Conflict Probing Rule + Resolution Capture — Design

**Date:** 2026-07-01
**Status:** Approved for planning

## Problem

Two gaps surfaced while testing conflict-resolution sessions:

1. **No requirement is collected.** `_extract_and_track_saturation` returns early for
   `kind == "conflict_resolution"` ([backend/app/routers/dialogue.py:147](../../../backend/app/routers/dialogue.py)),
   so nothing said in a conflict chat is ever captured. The RE's right-hand panel
   stays on the empty "Live Requirements" state.

2. **Probing has no goal.** Conflict sessions reuse the interview `StrategySelector`
   ([backend/app/services/strategy_selector.py](../../../backend/app/services/strategy_selector.py)),
   whose `pivot` and `related_concept` strategies explicitly steer the model to
   *change the subject* to unrelated areas — directly fighting the stored conflict
   summary that says "Do not open a broad new elicitation on unrelated topics"
   ([backend/app/services/conflict_resolution.py:99](../../../backend/app/services/conflict_resolution.py)).

These are one feature: conflict probing should have an **end goal — resolve the
contradiction between requirements A and B** — and the **resolution the stakeholder
converges on is the artifact we "collect"** (not raw spec rows).

## Goals

- Give conflict-resolution sessions a dedicated, goal-directed probing rule set that
  drives toward resolving A vs B and never pivots to unrelated topics.
- Detect when a stakeholder has converged on a resolution, and capture that decision
  as a structured "resolution stance" linked to the conflict.
- Surface the captured stance to the stakeholder (in-chat card) and to the RE
  (Conflicts panel + the in-chat right panel), and feed it into `ResolutionSuggester`.

## Non-goals

- **No new spec requirements minted from conflict chats.** We capture the *resolution
  decision*, not arbitrary new requirements. (Chosen over "same as interviews" to keep
  the SRS clean and avoid spawning fresh conflicts mid-resolution.)
- No change to the RE's suggest → propose → vote → apply flow other than feeding it the
  captured stances.
- No auto-apply. The RE still reviews and commits the reconciled wording.

## Design overview

```
stakeholder turn (conflict session)
   │
   ├─ ResolutionTracker (LLM)  → { reached, decision, statement }
   │       └─ if reached: upsert conflict.resolutions[stakeholder_id]
   │                      set session.wrap_up_suggested = true  (pauses probing)
   │
   └─ if not reached: QuestionGenerator with CONFLICT strategy set
           clarify_intent_a → clarify_intent_b → weigh_priority
           → explore_middle_ground → confirm_resolution (hold)
```

## Component 1 — Conflict probing rule

**Strategies** (new entries in
[backend/app/prompts/strategy_prompts.json](../../../backend/app/prompts/strategy_prompts.json)):

- `clarify_intent_a` — ask *why* requirement A matters / what breaks without it; reference A by name.
- `clarify_intent_b` — ask about the need behind requirement B; reference B by name.
- `weigh_priority` — ask which matters more in practice, or under what conditions each should apply (a context split).
- `explore_middle_ground` — propose or ask for a concrete compromise that could satisfy both (scope by context, threshold, or phase).
- `confirm_resolution` — restate the emerging resolution as ONE concrete option and ask the stakeholder to confirm it (one wins / compromise / restatement).

**Selection** — a deterministic progression driven by the count of agent turns already
in the session, cycling through the five above and then holding on
`confirm_resolution`. Implemented as a `ConflictStrategySelector` (sibling to
`StrategySelector`) or a `choose_conflict()` method — no short-reply / NFR / pivot
heuristics, so it never steers off-topic.

**Wiring** — `QuestionGenerator.next_question` takes the session `kind`. For
`conflict_resolution` it selects from the conflict strategies and the conflict prompt
set; the existing 14-mistake guard and the stored conflict `summary` still apply.
`dialogue.py` passes `kind=session["kind"]` from both `post_turn` and `post_question`.

*Rejected alternative:* a standalone `ConflictQuestionGenerator` — duplicates the
mistake-guard and generation machinery for no benefit.

## Component 2 — Resolution detection & capture

**New service** `backend/app/services/resolution_tracker.py` (mirrors
`RequirementExtractor`'s JSON-mode shape):

```python
async def track(*, statement_a, statement_b, explanation, transcript, same_stakeholder) -> dict
# returns { "reached": bool,
#           "decision": "a_wins" | "b_wins" | "compromise" | "restate" | None,
#           "statement": str | None }   # one-sentence restatement of the resolution
```

**Integration** — in the `kind == "conflict_resolution"` branch of
`_extract_and_track_saturation`:

1. Load the conflict (`session["conflict_id"]`), its requirement A/B statements, and
   `same_stakeholder`.
2. Run `ResolutionTracker.track(...)` over the transcript including the new turn.
3. If `reached`: upsert the stance and set `wrap_up_suggested = True`; return `True`.
4. If not reached (or the tracker errors): return `False` — probing continues.

Best-effort: any tracker exception is swallowed and treated as "not reached" (same
pattern as `RequirementExtractor`).

Reaching a resolution reuses the existing **`wrap_up_suggested`** mechanism (commit
8981d3b) to pause probing-question generation. The InputBox wrap-up banner becomes
kind-aware: for conflict sessions it reads e.g. "Sounds like you've settled on a
direction — confirm it, or keep discussing?" ("I'm done" still finishes the session).

## Component 3 — Data model

**`db.conflicts`** gains a `resolutions` sub-document, keyed by stakeholder id, mirroring
the existing `votes` shape:

```
resolutions: {
  "<stakeholder_id>": {
    "decision":    "a_wins" | "b_wins" | "compromise" | "restate",
    "statement":   "<one-sentence restatement>",
    "session_id":  "<conflict_resolution session id>",
    "captured_at": <datetime>
  }
}
```

Re-running the tracker on later turns overwrites the stance (the stakeholder may change
their mind). No new required field on `db.sessions`; `wrap_up_suggested` is reused.

## Component 4 — API changes

- **`ConflictOut`** ([backend/app/schemas/conflict.py](../../../backend/app/schemas/conflict.py))
  gains `resolutions: list[ResolutionStanceOut]` (`stakeholder` name, `decision`,
  `statement`, `captured_at`), populated in `_conflict_to_out` by resolving each
  stakeholder id to a name (as votes already do).
- **`ResolutionCardOut`** (`GET /sessions/{sid}/resolution`) gains
  `my_resolution: ResolutionStanceOut | None` — the captured stance for this session's
  stakeholder, so the stakeholder card can render and persist it across reloads.
- **`MessageResponse` / `TurnResponse`** ([backend/app/schemas/dialogue.py](../../../backend/app/schemas/dialogue.py))
  gain optional `resolution: ResolutionStanceOut | None` so the card appears immediately
  after the turn that captures it.
- **`ResolutionSuggester.suggest`** accepts the captured `resolutions` and includes them
  in its prompt as explicit decision signals (stronger than raw transcript).

## Component 5 — Frontend surfacing

- **Types** ([frontend/src/api/conflicts.ts](../../../frontend/src/api/conflicts.ts)):
  add `ResolutionStance`; add `resolutions` to `Conflict`; add `my_resolution` to
  `ResolutionCard`. Add optional `resolution` to the message response type in
  [frontend/src/api/sessions.ts](../../../frontend/src/api/sessions.ts).
- **Stakeholder** — a new "Resolution recorded" card in the conflict chat (sibling to
  `ResolutionVoteCard`) showing the captured decision + restatement. Rendered in the
  stakeholder column of [frontend/src/pages/MainPage.tsx](../../../frontend/src/pages/MainPage.tsx).
- **RE in-chat right panel** — a new `ConflictResolutionPanel` component rendered in
  place of `LiveRequirements` when the active session's `kind` is `conflict_resolution`.
  It shows the captured stance(s) for the conflict behind this session. Data is obtained
  by matching the active session id against `listConflicts(projectId)` →
  `resolution_sessions` (reuses existing endpoints; no new RE endpoint needed). Interview
  sessions keep the normal `LiveRequirements` panel.
- **RE Conflicts panel** ([frontend/src/components/Conflicts/ConflictsPanel.tsx](../../../frontend/src/components/Conflicts/ConflictsPanel.tsx))
  — render each stakeholder's captured stance under the conflict, alongside the existing
  resolution-chat links and votes.

## Error handling

- Tracker LLM failure → "not reached", probing continues (never blocks the reply).
- Missing/removed conflict or requirement behind a conflict session → skip capture, no error.
- Stance upsert is idempotent per (conflict, stakeholder); last write wins.

## Testing

- **Unit:** `ConflictStrategySelector` progression order; `ResolutionTracker` JSON parse
  and error-swallowing with a mocked LLM.
- **Router/integration:** a conflict turn that reaches resolution upserts
  `conflict.resolutions` and sets `wrap_up_suggested`; `ConflictOut` includes
  `resolutions`; `GET /sessions/{sid}/resolution` returns `my_resolution`; suggester
  prompt includes the stances.
- **Frontend:** `ConflictResolutionPanel` renders captured stances; the stakeholder
  "Resolution recorded" card renders when `my_resolution` is present; interview sessions
  still render `LiveRequirements`.

## Future work (out of scope)

- Capturing genuinely-new side requirements revealed mid-conflict (the "Resolution + new
  needs" option) — deferred; capture resolution only for now.
- Auto-reconciling both requirements on apply (the existing single-sided-merge limitation
  noted in the conflict-resolution strategy doc).
