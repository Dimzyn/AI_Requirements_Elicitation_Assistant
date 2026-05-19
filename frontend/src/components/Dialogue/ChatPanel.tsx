import { useEffect, useRef } from "react";
import { useSessionStore } from "../../store/sessionStore";
import StatusIndicator from "./StatusIndicator";

export default function ChatPanel() {
  const turns = useSessionStore((s) => s.turns);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length]);

  if (turns.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
        Describe what you want to build to start the interview.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-3">
      {turns.map((t) => (
        <div
          key={t.id}
          data-role={t.role}
          className={`flex ${t.role === "stakeholder" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
              t.role === "stakeholder"
                ? "bg-indigo-600 text-white"
                : "bg-white border text-slate-800"
            }`}
          >
            {t.role === "agent" && t.strategy && (
              <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">
                {t.strategy.replace("_", " ")}
              </div>
            )}
            {t.content}
          </div>
        </div>
      ))}
      <div className="pt-2"><StatusIndicator /></div>
      <div ref={bottomRef} />
    </div>
  );
}
