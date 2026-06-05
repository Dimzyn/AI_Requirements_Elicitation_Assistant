import { useState } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { createSession, postMessage, postQuestion, getRequirements } from "../../api/sessions";
import type { Turn } from "../../api/sessions";
import { GREETING } from "../../constants";

const DEFAULT_COUNT = 1;
const MIN_COUNT = 1;
const MAX_COUNT = 5;

function describeError(err: unknown): string {
  const e = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
  const status = e?.response?.status;
  const detail = e?.response?.data?.detail;
  if (status === 429) return "Gemini API rate limit reached. Wait a minute and try again.";
  if (status === 503) return "Gemini is temporarily overloaded. Try again in a few seconds.";
  if (status === 401) return "You've been signed out. Refresh the page.";
  if (detail) return String(detail);
  return e?.message ?? "Something went wrong.";
}

export default function InputBox() {
  const { activeId, draft, sessions, setStatus, appendTurns, setRequirements } = useSessionStore();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [count, setCount] = useState(DEFAULT_COUNT);
  const [error, setError] = useState<string | null>(null);

  // Render the input when a session is active or when we're in the draft welcome state.
  if (!activeId && !draft) return null;

  const activeSession = activeId ? sessions.find((s) => s.id === activeId) : undefined;
  const isArchived = activeSession ? activeSession.status !== "active" : false;

  if (isArchived) {
    return (
      <div className="border-t border-border bg-surface-muted px-4 py-3 text-center text-xs text-muted">
        This session is archived. Restore it from the sidebar to continue the conversation.
      </div>
    );
  }

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = text.trim();
    if (!content || busy) return;

    setBusy(true);
    setError(null);
    setText("");

    // Resolve the target session. In draft mode, create it now (the backend
    // seeds the greeting turn); otherwise send to the active session.
    let sid = activeId;
    if (!sid) {
      try {
        const s = await createSession();
        sid = s.id;
        const store = useSessionStore.getState();
        useSessionStore.setState({ sessions: [s, ...store.sessions] });
        store.setSkipNextTurnLoad(true);
        store.setActive(s.id); // clears turns, leaves draft mode
        // Seed the greeting locally so it survives the round-trip (it's also in the DB).
        store.setTurns([
          { id: `greeting-${s.id}`, role: "agent", content: GREETING, created_at: new Date().toISOString() },
        ]);
      } catch (err) {
        setText(content);
        setError(describeError(err));
        setBusy(false);
        return;
      }
    }

    const session_id = sid as string;

    const tempId = `temp-${Date.now()}`;
    const optimistic: Turn = {
      id: tempId,
      role: "stakeholder",
      content,
      created_at: new Date().toISOString(),
    };
    appendTurns([optimistic]);

    setStatus("validating");
    try {
      const { stakeholder_turn_id, session_title } = await postMessage(session_id, content);
      useSessionStore.setState((s) => ({
        turns: s.turns.map((t) => (t.id === tempId ? { ...t, id: stakeholder_turn_id } : t)),
        // Reflect the auto-generated name in the sidebar without a refetch.
        sessions: session_title
          ? s.sessions.map((se) => (se.id === session_id ? { ...se, project_title: session_title } : se))
          : s.sessions,
      }));
    } catch (err) {
      // /messages failed — roll back the optimistic bubble and restore the textbox.
      useSessionStore.setState((s) => ({ turns: s.turns.filter((t) => t.id !== tempId) }));
      setText(content);
      setError(describeError(err));
      setStatus("idle");
      setBusy(false);
      return;
    }

    // Best-effort: refresh requirements after extraction. Don't block the question loop on this.
    getRequirements(session_id).then(setRequirements).catch(() => {});

    setStatus("thinking");
    const results = await Promise.allSettled(
      Array.from({ length: count }, () => postQuestion(session_id))
    );
    const agentTurns: Turn[] = [];
    const failures: unknown[] = [];
    for (const r of results) {
      if (r.status === "fulfilled") {
        agentTurns.push({
          id: r.value.id,
          role: "agent",
          content: r.value.content,
          strategy: r.value.strategy,
          created_at: new Date().toISOString(),
        });
      } else {
        failures.push(r.reason);
      }
    }
    if (agentTurns.length > 0) appendTurns(agentTurns);
    if (failures.length > 0) {
      setError(
        `${failures.length} of ${count} questions failed: ${describeError(failures[0])}`
      );
    }

    setStatus("idle");
    setBusy(false);
  };

  return (
    <form onSubmit={onSend} className="border-t border-border bg-surface p-3.5">
      {error && (
        <div className="mb-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          {error}
        </div>
      )}
      <div className="flex items-end gap-2.5 rounded-xl border border-border bg-surface p-2.5 transition focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/15">
        <textarea
          className="h-10 flex-1 resize-none bg-transparent text-sm text-foreground outline-none placeholder:text-muted/70"
          rows={2}
          placeholder="Describe what you want…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend(e);
            }
          }}
          disabled={busy}
        />
        <div className="flex flex-col items-end gap-1.5">
          <label
            className="flex items-center gap-1 text-[11px] text-muted"
            title="Questions per turn"
          >
            Qs
            <select
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              disabled={busy}
              className="rounded-md border border-border bg-surface px-1 py-0.5 text-[11px] text-foreground"
            >
              {Array.from(
                { length: MAX_COUNT - MIN_COUNT + 1 },
                (_, i) => MIN_COUNT + i
              ).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground shadow-sm transition hover:brightness-110 disabled:bg-accent/40"
          >
            Send
          </button>
        </div>
      </div>
    </form>
  );
}
