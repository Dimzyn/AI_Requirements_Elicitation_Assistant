import { useEffect, useState } from "react";
import { listSessions, createSession } from "../../api/sessions";
import { useSessionStore } from "../../store/sessionStore";

export default function SessionList() {
  const { sessions, setSessions, activeId, setActive } = useSessionStore();
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");

  const refresh = async () => {
    try {
      setSessions(await listSessions());
    } catch {
      // swallow; UI shows empty list
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const onCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    const s = await createSession(title.trim());
    setTitle("");
    setCreating(false);
    await refresh();
    setActive(s.id);
  };

  const active = sessions.filter((s) => s.status === "active");
  const archived = sessions.filter((s) => s.status !== "active");

  return (
    <aside className="border-r bg-white flex flex-col">
      <div className="p-4 border-b">
        <button
          onClick={() => setCreating((v) => !v)}
          className="w-full bg-indigo-600 text-white rounded p-2 text-sm font-medium hover:bg-indigo-700"
        >
          {creating ? "Cancel" : "New Session"}
        </button>
        {creating && (
          <form onSubmit={onCreate} className="mt-3 space-y-2">
            <input
              autoFocus
              className="w-full border rounded p-2 text-sm"
              placeholder="Project title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <button type="submit" className="w-full bg-slate-800 text-white rounded p-2 text-sm">
              Create
            </button>
          </form>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-sm">
        <div>
          <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">Active</h3>
          <ul className="space-y-1">
            {active.length === 0 && <li className="text-slate-400 italic">No active sessions</li>}
            {active.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => setActive(s.id)}
                  className={`w-full text-left px-2 py-1.5 rounded flex items-center gap-2 ${
                    activeId === s.id ? "bg-indigo-50 text-indigo-900" : "hover:bg-slate-100"
                  }`}
                >
                  <span className="h-2 w-2 rounded-full bg-emerald-500" />
                  <span className="truncate">{s.project_title}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        {archived.length > 0 && (
          <div>
            <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">Archived</h3>
            <ul className="space-y-1">
              {archived.map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => setActive(s.id)}
                    className={`w-full text-left px-2 py-1.5 rounded flex items-center gap-2 ${
                      activeId === s.id ? "bg-slate-100" : "hover:bg-slate-50"
                    } text-slate-500`}
                  >
                    <span className="h-2 w-2 rounded-full bg-slate-300" />
                    <span className="truncate">{s.project_title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
}
