import { useEffect, useState } from "react";
import { getResolutionCard, voteResolution, type ResolutionCard } from "../../api/conflicts";

// Fetches the conflict proposal for this resolution session and renders the
// Accept / Request-changes card. Only mounted for conflict-resolution sessions
// (the endpoint 404s for plain interviews); renders nothing before the RE has
// published a proposal.
export default function ResolutionVoteCard({ sessionId }: { sessionId: string }) {
  const [card, setCard] = useState<ResolutionCard | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [requesting, setRequesting] = useState(false);

  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional reset before re-fetching when sessionId changes
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
      setRequesting(false);
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
      {myChoice && (
        <p className="text-xs text-muted">
          {myChoice === "accept" ? "You accepted this wording." : "You requested changes."}
        </p>
      )}
      {error && <p className="text-xs text-danger">{error}</p>}
      {requesting ? (
        // The comment box belongs to the request-changes flow only — never shown for Accept.
        <div className="space-y-2">
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What would you change?"
            rows={2}
            autoFocus
            className="w-full resize-none rounded border border-border bg-background px-2 py-1.5 text-xs text-foreground"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() => vote("request_changes")}
              disabled={busy}
              className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-foreground transition hover:brightness-110 disabled:opacity-40"
            >
              {busy ? "Sending…" : "Submit request"}
            </button>
            <button
              onClick={() => {
                setRequesting(false);
                setComment("");
                setError(null);
              }}
              disabled={busy}
              className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <button
            onClick={() => vote("accept")}
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-foreground transition hover:brightness-110 disabled:opacity-40"
          >
            {myChoice === "accept" ? "Accepted ✓" : "Accept"}
          </button>
          <button
            onClick={() => setRequesting(true)}
            disabled={busy}
            className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
          >
            {myChoice === "request_changes" ? "Changes requested ✓" : "Request changes"}
          </button>
        </div>
      )}
    </div>
  );
}
