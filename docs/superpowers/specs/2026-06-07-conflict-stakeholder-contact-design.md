# Conflict Stakeholder Contact — Design

**Date:** 2026-06-07
**Status:** Approved (pending spec review)
**Builds on:** `docs/superpowers/specs/2026-06-07-conflict-detection-design.md`

## Problem

The conflict-detection feature surfaces pairs of contradicting requirements from
different stakeholders, and lets the requirements engineer (SRE) resolve or
dismiss them. But resolving a real conflict usually requires **negotiation with
the stakeholders who stated the conflicting requirements** — the SRE needs to go
back to them and ask how to reconcile.

Today there is no help for that step. The SRE has to manually compose an outreach
message for each stakeholder. This feature generates that message for them.

## Scope

**In scope:** a frontend-only helper that, for any detected conflict, generates a
ready-to-send, pre-written message for each involved stakeholder. The SRE copies
the message and sends it through their own channel (email/chat).

**Out of scope (consistent with prior decisions and YAGNI):**
- Any backend or database change. All data needed is already returned by the
  conflict API (`ConflictOut`: both requirement statements, stakeholder names,
  explanation).
- Sending email/notifications from the app (no SMTP/notification infrastructure
  exists; outreach stays out-of-band, matching the existing invite-link pattern).
- Showing stakeholder email addresses in the message.
- Tracking a "contacted" status/timestamp on the conflict.
- AI-generated wording (the message is a fixed template).

## Approach

Extend the existing `ConflictsPanel` component. No new routing or modal
infrastructure — the messages appear in an inline, expandable section within the
conflict card (the app has no modal component, and inline expansion matches the
existing card-based layout).

## Components

### 1. Message builder (pure function)

A pure helper, `buildContactMessage`, with no React or network dependencies, so
it is independently unit-testable (matching the existing `*.test.ts` pattern such
as `specStore.test.ts`).

Signature (TypeScript):

```typescript
function buildContactMessage(args: {
  stakeholderName: string | null;
  theirStatement: string;
  otherStatement: string;
  explanation: string;
  projectTitle: string;
}): string
```

Template:

```
Hi {greetingName},

While reviewing requirements for {projectTitle}, one of your requirements
appears to conflict with another stakeholder's:

• Your requirement: "{theirStatement}"
• Conflicting requirement: "{otherStatement}"

Why they conflict: {explanation}

Could you let us know how you'd like to resolve this?
```

- `greetingName` is `stakeholderName` when present, otherwise `there` (so the
  line reads "Hi there,").
- `projectTitle` falls back to "this project" if empty.

For a conflict between two **different** stakeholders, the builder is called once
per side: for stakeholder A, `theirStatement` = requirement A and
`otherStatement` = requirement B; for stakeholder B, the roles swap.

### 2. Same-stakeholder case

When both requirements in a conflict belong to the **same** stakeholder (one
person stated two contradictory things), the panel shows a **single** message
instead of two near-identical ones. A second pure helper handles this:

```typescript
function buildSelfContactMessage(args: {
  stakeholderName: string | null;
  statementA: string;
  statementB: string;
  explanation: string;
  projectTitle: string;
}): string
```

Template:

```
Hi {greetingName},

While reviewing requirements for {projectTitle}, two of your requirements
appear to contradict each other:

• "{statementA}"
• "{statementB}"

Why they conflict: {explanation}

Could you let us know how you'd like to reconcile these?
```

Two requirements are "from the same stakeholder" when both
`requirement_a.stakeholder` and `requirement_b.stakeholder` are non-null and
equal.

### 3. ConflictsPanel UI changes

- Each open-conflict card gets a **"Contact stakeholders"** button alongside the
  existing **Mark resolved** / **Dismiss** buttons.
- Clicking it toggles an inline expanded section under that card (tracked by a
  per-conflict `expandedId` in component state).
- The expanded section renders one block per message (two blocks for a
  cross-stakeholder conflict, one for a same-stakeholder conflict). Each block
  shows the stakeholder name as a heading, the generated message in a read-only
  multiline area, and a **Copy** button.
- **Copy** writes the message to the clipboard via `navigator.clipboard.writeText`
  and briefly shows a "Copied" confirmation on that button.
- `projectTitle` is passed into `ConflictsPanel` as a new optional prop from
  `ProjectDetailPage`, which already has `project.title`.

## Data flow

1. `ConflictsPanel` already holds the list of open `Conflict` objects (each with
   `requirement_a`, `requirement_b`, `explanation`, and stakeholder names).
2. On "Contact stakeholders", the panel decides cross- vs same-stakeholder, calls
   the relevant builder(s), and renders the message block(s).
3. No network calls. No state persisted.

## Error handling

- `navigator.clipboard` may reject (e.g. insecure context). The Copy handler
  catches failures and leaves the message visible so the SRE can select and copy
  manually; no crash.
- Missing stakeholder name → "Hi there,". Empty project title → "this project".

## Testing

- **Unit tests** (`buildContactMessage` / `buildSelfContactMessage`):
  - cross-stakeholder message contains the correct "your" vs "conflicting"
    statements and the explanation;
  - role-swap for the second stakeholder is correct;
  - missing name falls back to "there";
  - empty project title falls back to "this project";
  - same-stakeholder builder lists both statements once.
- **Build / type-check**: `tsc -b && vite build` must pass.
- **Manual**: detect a conflict, click "Contact stakeholders", confirm one or two
  correctly-worded messages appear with working Copy buttons.

## Files

- Create: `frontend/src/components/Conflicts/contactMessage.ts` (the two pure builders)
- Create: `frontend/src/components/Conflicts/contactMessage.test.ts` (unit tests)
- Modify: `frontend/src/components/Conflicts/ConflictsPanel.tsx` (button, expand state, message blocks, copy)
- Modify: `frontend/src/pages/ProjectDetailPage.tsx` (pass `projectTitle` prop)
