# Conflict Stakeholder Contact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the requirements engineer generate ready-to-send, copy-paste outreach messages for the stakeholders involved in a detected conflict.

**Architecture:** Frontend-only. Two pure, unit-tested message-builder functions assemble a static template from data the conflict API already returns; the existing `ConflictsPanel` gains a "Contact stakeholders" button that expands inline message blocks with Copy buttons. No backend or DB changes.

**Tech Stack:** React / TypeScript / Vite / Tailwind, with Vitest unit tests.

**Spec:** `docs/superpowers/specs/2026-06-07-conflict-stakeholder-contact-design.md`

---

### Task 1: Message-builder functions

Two pure functions that produce the outreach text. No React, no network — independently unit-testable.

**Files:**
- Create: `frontend/src/components/Conflicts/contactMessage.ts`
- Test: `frontend/src/components/Conflicts/contactMessage.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/components/Conflicts/contactMessage.test.ts
import { describe, expect, it } from "vitest";
import { buildContactMessage, buildSelfContactMessage } from "./contactMessage";

describe("buildContactMessage", () => {
  it("includes the stakeholder's own statement, the conflicting one, and the explanation", () => {
    const msg = buildContactMessage({
      stakeholderName: "Alice",
      theirStatement: "Auto-approve all refunds.",
      otherStatement: "All refunds require manager sign-off.",
      explanation: "Cannot both auto-approve and require sign-off.",
      projectTitle: "Refund System",
    });
    expect(msg).toContain("Hi Alice,");
    expect(msg).toContain("Refund System");
    expect(msg).toContain('Your requirement: "Auto-approve all refunds."');
    expect(msg).toContain('Conflicting requirement: "All refunds require manager sign-off."');
    expect(msg).toContain("Why they conflict: Cannot both auto-approve and require sign-off.");
  });

  it("falls back to 'there' when the name is missing", () => {
    const msg = buildContactMessage({
      stakeholderName: null,
      theirStatement: "A",
      otherStatement: "B",
      explanation: "x",
      projectTitle: "P",
    });
    expect(msg).toContain("Hi there,");
  });

  it("falls back to 'this project' when the title is empty", () => {
    const msg = buildContactMessage({
      stakeholderName: "Bob",
      theirStatement: "A",
      otherStatement: "B",
      explanation: "x",
      projectTitle: "",
    });
    expect(msg).toContain("requirements for this project,");
  });
});

describe("buildSelfContactMessage", () => {
  it("lists both of the stakeholder's statements once and asks to reconcile", () => {
    const msg = buildSelfContactMessage({
      stakeholderName: "Carol",
      statementA: "Export to PDF.",
      statementB: "Never store documents.",
      explanation: "Exporting requires temporarily storing the document.",
      projectTitle: "Docs App",
    });
    expect(msg).toContain("Hi Carol,");
    expect(msg).toContain("two of your requirements");
    expect(msg).toContain('"Export to PDF."');
    expect(msg).toContain('"Never store documents."');
    expect(msg).toContain("reconcile these?");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/Conflicts/contactMessage.test.ts`
Expected: FAIL — cannot resolve module `./contactMessage`

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/components/Conflicts/contactMessage.ts

function greeting(name: string | null): string {
  const trimmed = (name ?? "").trim();
  return trimmed.length > 0 ? trimmed : "there";
}

function projectLabel(title: string): string {
  const trimmed = (title ?? "").trim();
  return trimmed.length > 0 ? trimmed : "this project";
}

export function buildContactMessage(args: {
  stakeholderName: string | null;
  theirStatement: string;
  otherStatement: string;
  explanation: string;
  projectTitle: string;
}): string {
  const { stakeholderName, theirStatement, otherStatement, explanation, projectTitle } = args;
  return [
    `Hi ${greeting(stakeholderName)},`,
    ``,
    `While reviewing requirements for ${projectLabel(projectTitle)}, one of your requirements appears to conflict with another stakeholder's:`,
    ``,
    `• Your requirement: "${theirStatement}"`,
    `• Conflicting requirement: "${otherStatement}"`,
    ``,
    `Why they conflict: ${explanation}`,
    ``,
    `Could you let us know how you'd like to resolve this?`,
  ].join("\n");
}

export function buildSelfContactMessage(args: {
  stakeholderName: string | null;
  statementA: string;
  statementB: string;
  explanation: string;
  projectTitle: string;
}): string {
  const { stakeholderName, statementA, statementB, explanation, projectTitle } = args;
  return [
    `Hi ${greeting(stakeholderName)},`,
    ``,
    `While reviewing requirements for ${projectLabel(projectTitle)}, two of your requirements appear to contradict each other:`,
    ``,
    `• "${statementA}"`,
    `• "${statementB}"`,
    ``,
    `Why they conflict: ${explanation}`,
    ``,
    `Could you let us know how you'd like to reconcile these?`,
  ].join("\n");
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/Conflicts/contactMessage.test.ts`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Conflicts/contactMessage.ts frontend/src/components/Conflicts/contactMessage.test.ts
git commit -m "feat: add stakeholder-contact message builders for conflicts"
```

---

### Task 2: Wire "Contact stakeholders" into ConflictsPanel

Add the button, the inline expandable message blocks, and the Copy behavior. Pass `projectTitle` from the page.

**Files:**
- Modify: `frontend/src/components/Conflicts/ConflictsPanel.tsx` (full new content below)
- Modify: `frontend/src/pages/ProjectDetailPage.tsx` (pass `projectTitle` prop)

- [ ] **Step 1: Replace `ConflictsPanel.tsx` with the version below**

```tsx
// frontend/src/components/Conflicts/ConflictsPanel.tsx
import { useCallback, useEffect, useState } from "react";
import {
  detectConflicts,
  listConflicts,
  updateConflict,
  type Conflict,
} from "../../api/conflicts";
import { buildContactMessage, buildSelfContactMessage } from "./contactMessage";

type ContactBlock = { name: string; text: string };

function messagesFor(c: Conflict, projectTitle: string): ContactBlock[] {
  const a = c.requirement_a;
  const b = c.requirement_b;
  const sameStakeholder =
    a.stakeholder != null && b.stakeholder != null && a.stakeholder === b.stakeholder;

  if (sameStakeholder) {
    return [
      {
        name: a.stakeholder ?? "Stakeholder",
        text: buildSelfContactMessage({
          stakeholderName: a.stakeholder,
          statementA: a.statement,
          statementB: b.statement,
          explanation: c.explanation,
          projectTitle,
        }),
      },
    ];
  }

  return [
    {
      name: a.stakeholder ?? "Stakeholder A",
      text: buildContactMessage({
        stakeholderName: a.stakeholder,
        theirStatement: a.statement,
        otherStatement: b.statement,
        explanation: c.explanation,
        projectTitle,
      }),
    },
    {
      name: b.stakeholder ?? "Stakeholder B",
      text: buildContactMessage({
        stakeholderName: b.stakeholder,
        theirStatement: b.statement,
        otherStatement: a.statement,
        explanation: c.explanation,
        projectTitle,
      }),
    },
  ];
}

export default function ConflictsPanel({
  projectId,
  projectTitle,
}: {
  projectId: string;
  projectTitle: string;
}) {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hasRun, setHasRun] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

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

  async function onCopy(key: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((k) => (k === key ? null : k)), 1500);
    } catch {
      // clipboard blocked (e.g. insecure context) — leave the text visible for manual copy
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
                  onClick={() => setExpandedId((id) => (id === c.id ? null : c.id))}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted"
                >
                  {expandedId === c.id ? "Hide messages" : "Contact stakeholders"}
                </button>
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

              {expandedId === c.id && (
                <div className="space-y-2 border-t border-border pt-2">
                  {messagesFor(c, projectTitle).map((m, i) => {
                    const key = `${c.id}-${i}`;
                    return (
                      <div key={key} className="rounded-md border border-border bg-surface p-2 space-y-1">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-medium text-accent">Message to {m.name}</p>
                          <button
                            onClick={() => onCopy(key, m.text)}
                            className="rounded border border-border px-2 py-1 text-xs font-medium text-foreground transition hover:bg-surface-muted"
                          >
                            {copiedKey === key ? "Copied" : "Copy"}
                          </button>
                        </div>
                        <textarea
                          readOnly
                          value={m.text}
                          rows={9}
                          className="w-full resize-none rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground"
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Pass `projectTitle` from `ProjectDetailPage.tsx`**

Find the existing line:

```tsx
          {/* Conflicts section */}
          <ConflictsPanel projectId={id} />
```

Replace it with:

```tsx
          {/* Conflicts section */}
          <ConflictsPanel projectId={id} projectTitle={project.title} />
```

(`project` is guaranteed non-null here — the component early-returns a loading state when `project` is null, before this render path.)

- [ ] **Step 3: Type-check and build**

Run: `cd frontend && npx tsc -b && npm run build`
Expected: no type errors; build succeeds

- [ ] **Step 4: Run the full frontend unit-test suite**

Run: `cd frontend && npm run test`
Expected: PASS (all existing tests plus the 4 new `contactMessage` tests)

- [ ] **Step 5: Manual verification**

Start the app (or `docker compose up -d --build`). As the requirements engineer, open a project with at least one detected conflict, click **Contact stakeholders** on a conflict card, and confirm:
- two message blocks appear for a cross-stakeholder conflict (one per stakeholder), each naming the right person and quoting the correct "your" vs "conflicting" requirement;
- the **Copy** button copies the text and briefly shows "Copied";
- clicking **Hide messages** collapses the section.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/Conflicts/ConflictsPanel.tsx frontend/src/pages/ProjectDetailPage.tsx
git commit -m "feat: add Contact stakeholders action with copyable messages to conflicts"
```

---

## Self-review notes

- **Spec coverage:** message builder (Task 1) + same-stakeholder collapse (Task 1 `buildSelfContactMessage`, wired in Task 2 `messagesFor`) + inline expand/Copy UI + `projectTitle` prop (Task 2) + clipboard-failure tolerance (Task 2 `onCopy` try/catch) + name/title fallbacks (Task 1) + unit tests + build/manual checks. All spec sections map to a task.
- **Type consistency:** `Conflict`, `RequirementRef` come from `../../api/conflicts`; `stakeholder` is `string | null`, matching the builder arg types. `buildContactMessage` / `buildSelfContactMessage` signatures are identical across Task 1 and Task 2.
- **No backend/DB changes**, per the spec.
