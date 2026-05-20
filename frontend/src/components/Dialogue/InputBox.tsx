import { useState } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { postMessage, postQuestion, getRequirements } from "../../api/sessions";
import type { Turn } from "../../api/sessions";

const DEFAULT_COUNT = 1;
const MIN_COUNT = 1;
const MAX_COUNT = 5;

function describeError(err: unknown): string {
  const e = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
  const status = e?.response?.status;
  const detail = e?.response?.data?.detail;
  if (status === 429) return "Gemini API rate limit reached. Wait a minute and try again.";
  if (status === 401) return "You've been signed out. Refresh the page.";
  if (detail) return String(detail);
  return e?.message ?? "Something went wrong.";
}

export default function InputBox() {
  const { activeId, sessions, setStatus, appendTurns, setRequirements } = useSessionStore();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [count, setCount] = useState(DEFAULT_COUNT);
  const [error, setError] = useState<string | null>(null);

  if (!activeId) return null;

  const activeSession = sessions.find((s) => s.id === activeId);
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
      const { stakeholder_turn_id } = await postMessage(activeId, content);
      useSessionStore.setState((s) => ({
        turns: s.turns.map((t) => (t.id === tempId ? { ...t, id: stakeholder_turn_id } : t)),
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
    getRequirements(activeId).then(setRequirements).catch(() => {});

    setStatus("thinking");
    const results = await Promise.allSettled(
      Array.from({ length: count }, () => postQuestion(activeId))
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
