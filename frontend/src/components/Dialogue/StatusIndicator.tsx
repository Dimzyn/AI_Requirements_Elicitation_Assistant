import { useSessionStore } from "../../store/sessionStore";

export default function StatusIndicator() {
  const status = useSessionStore((s) => s.status);
  if (status === "idle") return null;
  const label =
    status === "thinking"
      ? "Generating probing question…"
      : "Validating question relevance…";
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-muted shadow-card">
      <span className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:-0.2s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent [animation-delay:-0.1s]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent" />
      </span>
      {label}
    </div>
  );
}
