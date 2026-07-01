import { useEffect, useState } from "react";
import { getResolutionCard, type ResolutionStance } from "../../api/conflicts";
import { resolutionLabel } from "../Conflicts/resolutionLabel";

// Self-contained: fetches the captured resolution stance for this conflict session.
// Renders nothing for interview sessions (the endpoint 404s) or before a resolution
// has been captured.
export default function ResolutionRecordedCard({ sessionId }: { sessionId: string }) {
  const [stance, setStance] = useState<ResolutionStance | null>(null);

  // Fetch on session change, then poll — the stance is written mid-conversation by
  // the backend, so a one-shot fetch would miss it (mirrors MainPage's poll cadence).
  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional reset before re-fetching when sessionId changes
    setStance(null);
    const fetchStance = () =>
      getResolutionCard(sessionId)
        .then((c) => {
          if (alive) setStance(c.my_resolution);
        })
        .catch(() => {
          if (alive) setStance(null);
        });
    fetchStance();
    const id = setInterval(() => {
      if (!document.hidden) fetchStance();
    }, 6000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [sessionId]);

  if (!stance) return null;

  return (
    <div className="mx-6 mb-3 rounded-xl border border-border bg-surface p-3 shadow-card space-y-1">
      <p className="text-xs font-medium text-accent">Resolution recorded ✓</p>
      <p className="text-xs text-muted">{resolutionLabel(stance.decision)}</p>
      {stance.statement && <p className="text-sm text-foreground">{stance.statement}</p>}
      <p className="text-xs text-muted">Shared with your requirements engineer.</p>
    </div>
  );
}
