import { useState } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { postTurn, getTurns, getRequirements } from "../../api/sessions";

export default function InputBox() {
  const { activeId, setStatus, setTurns, setRequirements } = useSessionStore();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  if (!activeId) return null;

  const onSend = async (e: React.FormEvent) => {
    e.preventDefault();
    const content = text.trim();
    if (!content || busy) return;
    setBusy(true);
    setStatus("thinking");
    try {
      setText("");
      await postTurn(activeId, content, 5);
      setStatus("validating");
      // refresh full state
      const [turns, reqs] = await Promise.all([
        getTurns(activeId),
        getRequirements(activeId),
      ]);
      setTurns(turns);
      setRequirements(reqs);
    } catch (err) {
      // restore text if call failed
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
