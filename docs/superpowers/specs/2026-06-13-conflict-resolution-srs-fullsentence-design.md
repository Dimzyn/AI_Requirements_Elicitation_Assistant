# Conflict-Resolution Chats, SRS Export & Full-Sentence Requirements — Design

**Date:** 2026-06-13
**Status:** Implemented
**Builds on:** `2026-06-07-conflict-detection-design.md`, `2026-06-07-conflict-stakeholder-contact-design.md`

## Problem

Three gaps in the elicitation tool:

1. **Conflicts were detected but not resolvable in-app.** `ConflictsPanel` could
   detect contradicting requirements and generate a copy-paste outreach message,
   but a stakeholder had no in-app way to actually work through the conflict.
2. **No real SRS export.** The only export was a flat per-session bullet list
   (`compile_markdown`).
3. **Extracted requirements were terse fragments** ("Sync to-do items with Google
   Calendar.") rather than complete sentences.

## Decisions

- A resolution chat is **auto-created when conflict detection finds a conflict**
  (idempotent — re-detecting never duplicates).
- A cross-stakeholder conflict opens **one chat per involved stakeholder**; a
  same-stakeholder conflict opens **one**.
- The RE **still manually marks** a conflict resolved/dismissed after reading the
  chat — the existing lifecycle stays authoritative.

## Feature 1 — Auto conflict-resolution chats

- Sessions gain `kind` (`"interview"` | `"conflict_resolution"`) and `conflict_id`.
  Legacy docs without `kind` read as interview.
- `services/conflict_resolution.py` holds pure builders: `build_resolution_opener`
  / `build_self_resolution_opener` (the AI's first chat turn, two framings) and
  `build_resolution_summary` (stored on the session so the existing
  `QuestionGenerator` keeps follow-ups on-topic). Template-based — no LLM call, so
  detection stays fast and reliable.
- `routers/conflicts.py::detect_conflicts` calls `_ensure_resolution_sessions` for
  each **open** conflict: resolve each requirement → session → stakeholder, then
  idempotently create one resolution session (keyed by conflict + stakeholder)
  with an opening agent turn. `ConflictOut.resolution_sessions` exposes the chats
  so the panel can link to them.
- `routers/dialogue.py` **skips requirement extraction** for resolution chats —
  they clarify, they don't mint new spec rows; the RE edits the canonical
  requirement after reading.
- `routers/sessions.py::open_my_session` now scopes the "one session per project"
  lookup to non-resolution sessions, so a stakeholder's project never resolves to
  a resolution chat.
- Frontend: `ProjectSidebar` lists each project's resolution chats (and polls so a
  newly-opened chat appears without reload); `ConflictsPanel` links each conflict
  to its resolution chats for the RE to review before marking resolved.

## Feature 2 — Project-wide SRS export

- `services/export_service.py::compile_srs` renders an IEEE-830-style Markdown
  document (1. Introduction → Purpose/Background/Scope; 2. Specific Requirements →
  2.1 Functional / 2.2 Non-Functional / 2.3 Constraints with FR-/NFR-/CON-
  numbering, priority, stakeholder source, acceptance criteria). Rejected
  requirements are excluded. `srs_to_text` strips markers for `.txt`.
- `GET /projects/{pid}/export` (RE-only, owns project) aggregates every
  non-rejected requirement across the project's sessions with stakeholder
  attribution. `compile_markdown` and the per-session export are untouched.
- Frontend: an **Export SRS** (.md/.txt) control on the spec page toolbar.

## Feature 3 — Full-sentence extraction

- `services/requirement_extractor.py` prompt rewritten so statements are complete
  sentences ("Users can browse the menu and place an order.", "The system should
  support up to 50,000 concurrent orders during peak hours.") instead of
  fragments. Classification rules, the ≤3 quantity rule, the JSON contract, and
  generation params are unchanged; the dedup tokenizer already strips the added
  boilerplate words, so dedup is unaffected. Only new extractions change.

## Testing

- Backend `pytest`: 169 passing, including `test_conflict_resolution.py` (builders
  + same/cross-stakeholder creation + idempotency + extraction skip + session
  exposure) and SRS cases in `test_export.py`.
- Frontend: `npm run build` (tsc + vite) and `vitest run` (15) pass.

## Out of scope

Email/notifications; auto-resolving conflicts from chat content or writing the
reconciled wording back automatically; retroactively rewriting stored fragments.
