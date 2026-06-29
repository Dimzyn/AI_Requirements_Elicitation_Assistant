import { useEffect, useState } from "react";
import { getResolutionCard, voteResolution, type ResolutionCard } from "../../api/conflicts";

// Self-contained: fetches the conflict proposal for this resolution session and
// renders the Accept / Request-changes card. Renders nothing for normal interview
// sessions (the endpoint 404s) or before the RE has published a proposal.
export default function ResolutionVoteCard({ sessionId }: { sessionId: string }) {
  const [card, setCard] = useState<ResolutionCard | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setCard(null);
    getResolutionCard(sessionId)
      .then((c) => {
        if (alive) setCard(c);
      })
      .catch(() => {
        if (alive) setCard(null);
      });
    return () => {
      alive = false;
    };
  }, [sessionId]);

  if (!card || !card.proposal) return null;

  async function vote(choice: "accept" | "request_changes") {
    setError(null);
    setBusy(true);
    try {
      const updated = await voteResolution(sessionId, choice, comment || undefined);
      setCard(updated);
    } catch {
      setError("Couldn't record your vote — please try again.");
    } finally {
      setBusy(false);
    }
  }

  const myChoice = card.my_vote?.choice;
  return (
    <div className="mx-6 mb-3 rounded-xl border border-border bg-surface p-3 shadow-card space-y-2">
      <p className="text-xs font-medium text-accent">Proposed resolution — do you accept?</p>
      <p className="text-sm text-foreground">{card.proposal.statement}</p>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Optional: what would you change?"
        rows={2}
        className="w-full resize-none rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground"
      />
      {error && <p className="text-xs text-danger">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          onClick={() => vote("accept")}
          disabled={busy}
          className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-foreground transition hover:brightness-110 disabled:opacity-40"
        >
          {myChoice === "accept" ? "Accepted ✓" : "Accept"}
        </button>
        <button
          onClick={() => vote("request_changes")}
          disabled={busy}
          className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
        >
          {myChoice === "request_changes" ? "Changes requested ✓" : "Request changes"}
        </button>
      </div>
    </div>
  );
}
