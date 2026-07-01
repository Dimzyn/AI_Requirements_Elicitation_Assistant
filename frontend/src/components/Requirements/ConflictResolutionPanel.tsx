import { useEffect, useState } from "react";
import { listConflicts, type Conflict } from "../../api/conflicts";
import { matchConflictForSession } from "../Conflicts/matchConflictForSession";
import { resolutionLabel } from "../Conflicts/resolutionLabel";

// The RE's right-hand panel while observing a conflict-resolution chat: shows the
// two clashing requirements and any resolution stances captured from stakeholders.
export default function ConflictResolutionPanel({
  projectId,
  sessionId,
}: {
  projectId: string;
  sessionId: string;
}) {
  const [conflict, setConflict] = useState<Conflict | null>(null);

  // Fetch then poll, so a stance captured while the RE watches this chat appears
  // without a manual reload (mirrors ConflictsPanel's polling cadence).
  useEffect(() => {
    let alive = true;
    const fetchConflict = () =>
      listConflicts(projectId)
        .then((all) => {
          if (alive) setConflict(matchConflictForSession(all, sessionId));
        })
        .catch(() => {
          if (alive) setConflict(null);
        });
    fetchConflict();
    const id = setInterval(() => {
      if (!document.hidden) fetchConflict();
    }, 6000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [projectId, sessionId]);

  return (
    <aside className="flex min-h-0 flex-col gap-3.5 overflow-y-auto border-l border-border bg-surface p-4">
      <h2 className="shrink-0 text-sm font-semibold text-foreground">Resolution</h2>
      {!conflict ? (
        <p className="text-sm italic text-muted">No conflict data for this chat.</p>
      ) : (
        <>
          <div className="shrink-0 space-y-2 rounded-xl border border-border bg-surface p-3">
            <p className="text-xs font-medium text-accent">Conflicting requirements</p>
            <p className="text-sm text-foreground">A: {conflict.requirement_a.statement}</p>
            <p className="text-sm text-foreground">B: {conflict.requirement_b.statement}</p>
            <p className="text-xs italic text-muted">{conflict.explanation}</p>
          </div>
          <div className="shrink-0 space-y-2">
            <p className="text-xs font-semibold text-foreground">Captured resolutions</p>
            {conflict.resolutions.length === 0 ? (
              <p className="text-sm italic text-muted">No resolution captured yet.</p>
            ) : (
              conflict.resolutions.map((s, i) => (
                <div key={i} className="rounded-lg border border-border bg-background p-3 space-y-1">
                  <p className="text-xs font-medium text-accent">{s.stakeholder ?? "Stakeholder"}</p>
                  <p className="text-xs text-muted">{resolutionLabel(s.decision)}</p>
                  {s.statement && <p className="text-sm text-foreground">{s.statement}</p>}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </aside>
  );
}
