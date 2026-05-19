import { useState } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { postMessage, postQuestion, getRequirements } from "../../api/sessions";
import type { Turn } from "../../api/sessions";

const QUESTIONS_PER_TURN = 5;

export default function InputBox() {
  const { activeId, setStatus, appendTurns, setRequirements } = useSessionStore();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  if (!activeId) return null;

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = text.trim();
    if (!content || busy) return;

    setBusy(true);
    setText("");

    // 1) Optimistic stakeholder bubble — shows immediately.
    const tempId = `temp-${Date.now()}`;
    const optimistic: Turn = {
      id: tempId,
      role: "stakeholder",
      content,
      created_at: new Date().toISOString(),
    };
    appendTurns([optimistic]);

    try {
      // 2) Persist stakeholder turn + extract requirements (fast).
      setStatus("validating");
      const { stakeholder_turn_id } = await postMessage(activeId, content);

      // Reconcile the optimistic id with the real one.
      useSessionStore.setState((s) => ({
        turns: s.turns.map((t) =>
          t.id === tempId ? { ...t, id: stakeholder_turn_id } : t
        ),
      }));

      // Refresh requirements once after extraction.
      getRequirements(activeId).then(setRequirements).catch(() => {});

      // 3) Stream probing questions in one at a time.
      setStatus("thinking");
      for (let i = 0; i < QUESTIONS_PER_TURN; i++) {
        const q = await postQuestion(activeId);
        const agentTurn: Turn = {
          id: q.id,
          role: "agent",
          content: q.content,
          strategy: q.strategy,
          created_at: new Date().toISOString(),
        };
        appendTurns([agentTurn]);
      }
    } catch (err) {
      // restore the input so the user can retry
      setText(content);
    } finally {
      setStatus("idle");
      setBusy(false);
    }
  };

  return (
    <form onSubmit={onSend} className="border-t bg-white p-4 flex gap-2">
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
      <button
        type="submit"
        disabled={busy || !text.trim()}
        className="self-end bg-indigo-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-indigo-700 disabled:bg-slate-300"
      >
        Send
      </button>
    </form>
  );
}
