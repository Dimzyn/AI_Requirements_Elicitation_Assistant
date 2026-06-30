import { useSessionStore } from "../../store/sessionStore";
import { exportSession } from "../../api/sessions";

const TYPE_LABEL: Record<string, string> = {
  functional: "⚙ Functional",
  non_functional: "◷ Non-Functional",
  constraint: "⊘ Constraints",
};

export default function LiveRequirements() {
  const { activeId, requirements, sessions } = useSessionStore();

  const grouped = requirements.reduce<Record<string, typeof requirements>>((acc, r) => {
    (acc[r.type] ||= []).push(r);
    return acc;
  }, {});

  const onExport = async (format: "md" | "txt") => {
    if (!activeId) return;
    const blob = await exportSession(activeId, format);
    const title =
      sessions.find((s) => s.id === activeId)?.title?.replace(/\s+/g, "_") ?? "requirements";
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title}.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <aside className="flex min-h-0 flex-col gap-3.5 overflow-y-auto border-l border-border bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Live Requirements</h2>
        {activeId && (
          <div className="flex gap-1.5">
            <button
              onClick={() => onExport("md")}
              className="rounded-md border border-border px-2 py-1 text-[10px] text-muted transition hover:bg-surface-muted hover:text-foreground"
              title="Download as Markdown"
            >
              .md
            </button>
            <button
              onClick={() => onExport("txt")}
              className="rounded-md border border-border px-2 py-1 text-[10px] text-muted transition hover:bg-surface-muted hover:text-foreground"
              title="Download as plain text"
            >
              .txt
            </button>
          </div>
        )}
      </div>
      {Object.keys(TYPE_LABEL).map((k) => {
        const items = grouped[k] || [];
        if (items.length === 0) return null;
        return (
          <div key={k} className="overflow-hidden rounded-xl border border-border bg-surface">
            <div className="flex items-center justify-between border-b border-border bg-surface-muted px-3 py-2.5">
              <span className="text-[11px] font-semibold text-foreground">
                {TYPE_LABEL[k]}
              </span>
              <span className="rounded-full bg-accent/12 px-2 py-0.5 text-[10px] font-semibold text-accent">
                {items.length}
              </span>
            </div>
            <ul>
              {items.map((r) => (
                <li
                  key={r.id}
                  className="border-b border-border px-3 py-2.5 text-sm text-foreground last:border-b-0"
                >
                  {r.statement}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {requirements.length === 0 && (
        <p className="text-sm italic text-muted">No requirements extracted yet.</p>
      )}
    </aside>
  );
}
