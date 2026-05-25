import { useEffect, useRef } from "react";
import { useSessionStore } from "../../store/sessionStore";
import StatusIndicator from "./StatusIndicator";

const STRATEGY_DISPLAY: Record<string, { label: string; color: string }> = {
  concept: { label: "Drilling deeper", color: "bg-blue-100 text-blue-700" },
  related_concept: { label: "Broadening scope", color: "bg-purple-100 text-purple-700" },
  general: { label: "Clarifying", color: "bg-slate-100 text-slate-600" },
  nfr_probe: { label: "Probing NFRs", color: "bg-amber-100 text-amber-700" },
  pivot: { label: "Pivoting topic", color: "bg-emerald-100 text-emerald-700" },
};

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
              <span
                className={`inline-block text-[10px] font-medium px-1.5 py-0.5 rounded mb-1 ${
                  STRATEGY_DISPLAY[t.strategy]?.color ?? "bg-slate-100 text-slate-600"
                }`}
              >
                {STRATEGY_DISPLAY[t.strategy]?.label ?? t.strategy}
              </span>
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
