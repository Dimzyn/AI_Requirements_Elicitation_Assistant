import { useEffect, useRef } from "react";
import { useSessionStore } from "../../store/sessionStore";
import StatusIndicator from "./StatusIndicator";
import Badge, { type BadgeTone } from "../ui/Badge";

const STRATEGY_DISPLAY: Record<string, { label: string; tone: BadgeTone }> = {
  concept: { label: "Drilling deeper", tone: "info" },
  related_concept: { label: "Broadening scope", tone: "accent" },
  general: { label: "Clarifying", tone: "neutral" },
  nfr_probe: { label: "Probing NFRs", tone: "warning" },
  pivot: { label: "Pivoting topic", tone: "success" },
};

export default function ChatPanel() {
  const turns = useSessionStore((s) => s.turns);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length]);

  if (turns.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-muted">
        Describe what you want to build to start the interview.
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-3.5 overflow-y-auto p-6">
      {turns.map((t) => (
        <div
          key={t.id}
          data-role={t.role}
          className={`flex ${t.role === "stakeholder" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[74%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm shadow-card ${
              t.role === "stakeholder"
                ? "rounded-br-sm bg-accent text-accent-foreground"
                : "rounded-bl-sm border border-border bg-surface text-foreground"
            }`}
          >
            {t.role === "agent" && t.strategy && (
              <div>
                <Badge
                  tone={STRATEGY_DISPLAY[t.strategy]?.tone ?? "neutral"}
                  className="mb-1.5"
                >
                  {STRATEGY_DISPLAY[t.strategy]?.label ?? t.strategy}
                </Badge>
              </div>
            )}
            {t.content}
          </div>
        </div>
      ))}
      <div className="pt-2">
        <StatusIndicator />
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
