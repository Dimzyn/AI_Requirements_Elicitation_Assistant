import { useEffect } from "react";
import { useSessionStore } from "../../store/sessionStore";
import { getRequirements, getTurns } from "../../api/sessions";

const TYPE_LABEL: Record<string, string> = {
  functional: "Functional",
  non_functional: "Non-Functional",
  constraint: "Constraints",
};

export default function LiveRequirements() {
  const { activeId, requirements, setRequirements, setTurns } = useSessionStore();

  useEffect(() => {
    if (!activeId) return;
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

  return (
    <aside className="border-l bg-white p-4 overflow-y-auto">
      <h2 className="font-semibold mb-3">Live Requirements</h2>
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
