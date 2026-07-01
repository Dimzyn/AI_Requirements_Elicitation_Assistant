import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
import { resolutionLabel } from "./resolutionLabel";
import { buildContactMessage, buildSelfContactMessage } from "./contactMessage";

type SuggestState = {
  loading?: boolean;
  error?: string | null;
  suggestion?: string;
  rationale?: string;
};

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
  const [suggestState, setSuggestState] = useState<Record<string, SuggestState>>({});
  const [applyingKey, setApplyingKey] = useState<string | null>(null);
  const [proposingId, setProposingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const open = await listConflicts(projectId, "open");
      setConflicts(open);
    } catch {
      // a failed background list is non-fatal; keep whatever is shown
    }
  }, [projectId]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount; refresh loads the conflict list
    void refresh();
  }, [refresh]);

  // Poll so stakeholder votes (accept / request changes) surface on the RE's panel
  // without a manual reload. Mirrors the project page's polling cadence.
  useEffect(() => {
    const intervalId = setInterval(() => {
      if (!document.hidden) void refresh();
    }, 5000);
    return () => clearInterval(intervalId);
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
      setExpandedId((prev) => (prev === id ? null : prev));
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

  async function onSuggest(c: Conflict) {
    setSuggestState((prev) => ({ ...prev, [c.id]: { loading: true, error: null } }));
    try {
      const res = await suggestResolution(c.id);
      setSuggestState((prev) => ({
        ...prev,
        [c.id]: { loading: false, suggestion: res.suggestion, rationale: res.rationale },
      }));
    } catch {
      setSuggestState((prev) => ({
        ...prev,
        [c.id]: {
          loading: false,
          error: "Couldn't draft a suggestion. The AI service may be busy — try again.",
        },
      }));
    }
  }

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

              {c.resolution_sessions.length > 0 && (
                <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed border-border bg-surface px-2 py-1.5 text-xs">
                  <span className="text-muted">
                    AI resolution chats opened — review each reply, then mark resolved:
                  </span>
                  {c.resolution_sessions.map((rs) => (
                    <Link
                      key={rs.id}
                      to={`/chat?session=${rs.id}`}
                      className="rounded-md border border-border px-2 py-0.5 font-medium text-accent transition hover:bg-surface-muted"
                    >
                      {rs.stakeholder || "Stakeholder"}
                    </Link>
                  ))}
                </div>
              )}

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
                      {v.comment ? ` — "${v.comment}"` : ""}
                    </p>
                  ))}
                </div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => setExpandedId((id) => (id === c.id ? null : c.id))}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted"
                >
                  {expandedId === c.id ? "Hide messages" : "Contact stakeholders"}
                </button>
                <button
                  onClick={() => onSuggest(c)}
                  disabled={suggestState[c.id]?.loading}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
                >
                  {suggestState[c.id]?.loading ? "Drafting…" : "Suggest reconciled wording"}
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
                          aria-label={`Message to ${m.name}`}
                          value={m.text}
                          rows={9}
                          className="w-full resize-none rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground"
                        />
                      </div>
                    );
                  })}
                </div>
              )}

              {(() => {
                const ss = suggestState[c.id];
                if (!ss || (!ss.loading && !ss.error && ss.suggestion === undefined)) return null;
                return (
                  <div className="space-y-2 border-t border-border pt-2">
                    {ss.loading && (
                      <p className="text-xs text-muted">Drafting a reconciled requirement…</p>
                    )}
                    {ss.error && <p className="text-xs text-danger">{ss.error}</p>}
                    {ss.suggestion !== undefined && (
                      <>
                        <p className="text-xs font-medium text-accent">
                          Suggested reconciled requirement (editable)
                        </p>
                        <textarea
                          aria-label="Suggested reconciled requirement"
                          value={ss.suggestion}
                          onChange={(e) =>
                            setSuggestState((prev) => ({
                              ...prev,
                              [c.id]: { ...prev[c.id], suggestion: e.target.value },
                            }))
                          }
                          rows={3}
                          className="w-full resize-none rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground"
                        />
                        {ss.rationale && <p className="text-xs text-muted italic">{ss.rationale}</p>}
                        <div className="flex flex-wrap items-center gap-2">
                          <button
                            onClick={() => onPropose(c)}
                            disabled={proposingId === c.id || !ss.suggestion?.trim()}
                            className="rounded-md bg-accent px-2.5 py-1 text-xs font-semibold text-accent-foreground transition hover:brightness-110 disabled:opacity-40"
                          >
                            {proposingId === c.id ? "Sending…" : "Send to stakeholders"}
                          </button>
                          <span className="text-xs text-muted">Apply to:</span>
                          <button
                            onClick={() => onApply(c, c.requirement_a.id)}
                            disabled={applyingKey !== null || !ss.suggestion?.trim()}
                            className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
                          >
                            {applyingKey === `${c.id}-${c.requirement_a.id}`
                              ? "Applying…"
                              : `${c.requirement_a.stakeholder || "Stakeholder A"}'s statement`}
                          </button>
                          {c.requirement_b.id !== c.requirement_a.id && (
                            <button
                              onClick={() => onApply(c, c.requirement_b.id)}
                              disabled={applyingKey !== null || !ss.suggestion?.trim()}
                              className="rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
                            >
                              {applyingKey === `${c.id}-${c.requirement_b.id}`
                                ? "Applying…"
                                : `${c.requirement_b.stakeholder || "Stakeholder B"}'s statement`}
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                );
              })()}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
