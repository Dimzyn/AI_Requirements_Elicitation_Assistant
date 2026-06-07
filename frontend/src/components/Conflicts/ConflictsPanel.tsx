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
