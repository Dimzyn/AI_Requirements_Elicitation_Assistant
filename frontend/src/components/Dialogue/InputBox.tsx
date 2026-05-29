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
      <div className="border-t bg-slate-50 px-4 py-3 text-xs text-slate-600 text-center">
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
    <form onSubmit={onSend} className="border-t bg-white p-4">
      {error && (
        <div className="mb-2 px-3 py-2 bg-amber-50 border border-amber-200 text-amber-900 text-xs rounded">
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <textarea
          className="flex-1 border rounded p-2 text-sm resize-none"
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
        <div className="flex flex-col gap-1 items-stretch">
          <label className="text-[10px] text-slate-500 text-right" title="Questions per turn">
            Qs:&nbsp;
            <select
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              disabled={busy}
              className="border rounded text-xs px-1"
            >
              {Array.from({ length: MAX_COUNT - MIN_COUNT + 1 }, (_, i) => MIN_COUNT + i).map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={busy || !text.trim()}
            className="bg-indigo-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-indigo-700 disabled:bg-slate-300"
          >
            Send
          </button>
        </div>
      </div>
    </form>
  );
}
