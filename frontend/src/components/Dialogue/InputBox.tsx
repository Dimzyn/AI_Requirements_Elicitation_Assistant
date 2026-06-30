import { useLayoutEffect, useRef, useState } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { postMessage, postQuestion, finishSession } from "../../api/sessions";
import { useAuthStore } from "../../store/authStore";
import type { Turn } from "../../api/sessions";

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
  const { activeId, sessions, setStatus, appendTurns } = useSessionStore();
  const role = useAuthStore((s) => s.role);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [count, setCount] = useState(DEFAULT_COUNT);
  const [error, setError] = useState<string | null>(null);
  const [wrapUp, setWrapUp] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Grow the composer with its content up to a cap, then scroll within it — so a
  // long answer stays fully visible instead of being clamped to a single line.
  useLayoutEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  if (!activeId) {
    return (
      <div className="border-t border-border bg-surface-muted px-4 py-3 text-center text-xs text-muted">
        Select a project to start the interview.
      </div>
    );
  }

  const activeSession = sessions.find((s) => s.id === activeId);

  if (activeSession?.status === "completed" || activeSession?.stakeholder_finished) {
    return (
      <div className="border-t border-border bg-surface-muted px-4 py-3 text-center text-xs text-muted">
        {activeSession?.status === "completed"
          ? "This requirements elicitation has ended. Thank you!"
          : "You've marked this finished — thank you! Your engineer will review it."}
      </div>
    );
  }

  if (role === "requirements_engineer") {
    return (
      <div className="border-t border-border bg-surface-muted px-4 py-3 text-center text-xs text-muted">
        Read-only view — only the stakeholder can respond in this interview.
      </div>
    );
  }

  const session_id = activeId;

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = text.trim();
    if (!content || busy) return;

    setBusy(true);
    setError(null);
    setText("");

    const tempId = `temp-${Date.now()}`;
    const optimistic: Turn = {
      id: tempId,
      role: "stakeholder",
      content,
      created_at: new Date().toISOString(),
    };
    appendTurns([optimistic]);

    setStatus("validating");
    let wrapSuggested = false;
    try {
      const { stakeholder_turn_id, session_title, wrap_up_suggested } = await postMessage(
        session_id,
        content
      );
      wrapSuggested = !!wrap_up_suggested;
      useSessionStore.setState((s) => ({
        turns: s.turns.map((t) => (t.id === tempId ? { ...t, id: stakeholder_turn_id } : t)),
        // Reflect the auto-generated name in the sidebar without a refetch.
        sessions: session_title
          ? s.sessions.map((se) => (se.id === session_id ? { ...se, title: session_title } : se))
          : s.sessions,
      }));
      // The backend flags wrap-up on an explicit "I'm done" or after a few turns
      // with no new requirement; surface the gentle prompt.
      if (wrap_up_suggested) setWrapUp(true);
    } catch (err) {
      // /messages failed — roll back the optimistic bubble and restore the textbox.
      useSessionStore.setState((s) => ({ turns: s.turns.filter((t) => t.id !== tempId) }));
      setText(content);
      setError(describeError(err));
      setStatus("idle");
      setBusy(false);
      return;
    }

    // Wrapping up: pause probing-question generation. "Keep going" dismisses the
    // banner and the stakeholder's next message resumes generation.
    if (wrapSuggested) {
      setStatus("idle");
      setBusy(false);
      return;
    }

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

  const onFinish = async () => {
    setFinishing(true);
    try {
      await finishSession(session_id);
      // Locally mark finished so the composer locks immediately (the early-return
      // guard above renders the thank-you state on the next render).
      useSessionStore.setState((s) => ({
        sessions: s.sessions.map((se) =>
          se.id === session_id ? { ...se, stakeholder_finished: true } : se
        ),
      }));
      setWrapUp(false);
    } finally {
      setFinishing(false);
    }
  };

  return (
    <form onSubmit={onSend} className="border-t border-border bg-surface p-3.5">
      {wrapUp && (
        <div className="mb-2 flex items-center justify-between gap-2 rounded-lg border border-info/30 bg-info/10 px-3 py-2 text-xs text-foreground">
          <span>
            It sounds like we've covered a lot — anything else you'd like to add, or shall we wrap up?
          </span>
          <div className="flex shrink-0 gap-1.5">
            <button
              type="button"
              onClick={onFinish}
              disabled={finishing}
              className="rounded-md bg-accent px-2.5 py-1 font-medium text-accent-foreground transition hover:brightness-110 disabled:opacity-40"
            >
              {finishing ? "…" : "I'm done"}
            </button>
            <button
              type="button"
              onClick={() => setWrapUp(false)}
              className="rounded-md border border-border px-2.5 py-1 font-medium text-foreground transition hover:bg-surface-muted"
            >
              Keep going
            </button>
          </div>
        </div>
      )}
      {error && (
        <div className="mb-2 rounded-lg border border-warning/30 bg-warning/10 px-3 py-2 text-xs text-warning">
          {error}
        </div>
      )}
      <div className="flex items-end gap-2.5 rounded-xl border border-border bg-surface p-2.5 transition focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/15">
        <textarea
          ref={taRef}
          className="max-h-40 min-h-[2.5rem] flex-1 resize-none overflow-y-auto bg-transparent text-sm text-foreground outline-none placeholder:text-muted/70"
          rows={1}
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
