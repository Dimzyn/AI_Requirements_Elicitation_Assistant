import { useEffect } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { getRequirements, getTurns, exportSession } from "../../api/sessions";

const TYPE_LABEL: Record<string, string> = {
  functional: "Functional",
  non_functional: "Non-Functional",
  constraint: "Constraints",
};

export default function LiveRequirements() {
  const { activeId, requirements, setRequirements, setTurns, sessions } = useSessionStore();

  useEffect(() => {
    if (!activeId) return;
    // A session just created mid-send already has its turns set optimistically;
    // skip this one load so we don't clobber them, then resume normal loading.
    if (useSessionStore.getState().skipNextTurnLoad) {
      useSessionStore.getState().setSkipNextTurnLoad(false);
      return;
    }
    (async () => {
      try {
        const [turns, reqs] = await Promise.all([
          getTurns(activeId),
          getRequirements(activeId),
        ]);
        setTurns(turns);
        setRequirements(reqs);
      } catch {
        /* ignore */
      }
    })();
  }, [activeId]);

  const grouped = requirements.reduce<Record<string, typeof requirements>>((acc, r) => {
    (acc[r.type] ||= []).push(r);
    return acc;
  }, {});

  const onExport = async (format: "md" | "txt") => {
    if (!activeId) return;
    const blob = await exportSession(activeId, format);
    const title =
      sessions.find((s) => s.id === activeId)?.project_title?.replace(/\s+/g, "_") ?? "requirements";
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
    <aside className="border-l bg-white p-4 overflow-y-auto flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-semibold">Live Requirements</h2>
        {activeId && (
          <div className="flex gap-1">
            <button
              onClick={() => onExport("md")}
              className="text-xs px-2 py-1 border rounded hover:bg-slate-100"
              title="Download as Markdown"
            >
              .md
            </button>
            <button
              onClick={() => onExport("txt")}
              className="text-xs px-2 py-1 border rounded hover:bg-slate-100"
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
          <div key={k} className="mb-4">
            <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">
              {TYPE_LABEL[k]}
            </h3>
            <ul className="space-y-1 text-sm">
              {items.map((r) => (
                <li key={r.id} className="border-l-2 border-indigo-400 pl-2">
                  {r.statement}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {requirements.length === 0 && (
        <p className="text-slate-400 text-sm italic">No requirements extracted yet.</p>
      )}
    </aside>
  );
}
