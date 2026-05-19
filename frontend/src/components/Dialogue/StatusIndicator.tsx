import { useSessionStore } from "../../store/sessionStore";

export default function StatusIndicator() {
  const status = useSessionStore((s) => s.status);
  if (status === "idle") return null;
  const label = status === "thinking" ? "Generating probing question…" : "Validating question relevance…";
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-50 text-amber-800 text-xs">
      <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" />
      {label}
    </div>
  );
}
