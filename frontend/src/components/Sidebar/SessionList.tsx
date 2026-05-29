import { useEffect, useState } from "react";
import {
  listSessions,
  archiveSession,
  unarchiveSession,
  deleteSession,
} from "../../api/sessions";
import { useSessionStore } from "../../store/sessionStore";

export default function SessionList() {
  const { sessions, setSessions, activeId, setActive, draft, setDraft } = useSessionStore();
  const [busyId, setBusyId] = useState<string | null>(null);

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

  const onArchive = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setBusyId(id);
    try {
      await archiveSession(id);
      if (activeId === id) setActive(null);
      await refresh();
    } finally {
      setBusyId(null);
    }
  };

  const onUnarchive = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setBusyId(id);
    try {
      await unarchiveSession(id);
      await refresh();
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = async (id: string, projectTitle: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ok = window.confirm(
      `Permanently delete "${projectTitle}"?\n\nThis removes the session and all its turns and requirements. This cannot be undone.`
    );
    if (!ok) return;
    setBusyId(id);
    try {
      await deleteSession(id);
      if (activeId === id) setActive(null);
      await refresh();
    } finally {
      setBusyId(null);
    }
  };

  const active = sessions.filter((s) => s.status === "active");
  const archived = sessions.filter((s) => s.status !== "active");

  return (
    <aside className="border-r bg-white flex flex-col">
      <div className="p-4 border-b">
        <button
          onClick={() => setDraft(true)}
          disabled={draft && !activeId}
          className="w-full bg-indigo-600 text-white rounded p-2 text-sm font-medium hover:bg-indigo-700 disabled:bg-indigo-300"
        >
          New Session
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-3 space-y-4 text-sm">
        <div>
          <h3 className="text-xs uppercase tracking-wider text-slate-500 mb-2">Active</h3>
          <ul className="space-y-1">
            {active.length === 0 && <li className="text-slate-400 italic">No active sessions</li>}
            {active.map((s) => (
              <li key={s.id}>
                <div
                  onClick={() => setActive(s.id)}
                  className={`group cursor-pointer px-2 py-1.5 rounded flex items-center gap-2 ${
                    activeId === s.id ? "bg-indigo-50 text-indigo-900" : "hover:bg-slate-100"
                  }`}
                >
                  <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" />
                  <span className="truncate flex-1">{s.project_title}</span>
                  <button
                    onClick={(e) => onArchive(s.id, e)}
                    disabled={busyId === s.id}
                    className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-slate-900 text-xs px-1.5 py-0.5 rounded hover:bg-white border border-transparent hover:border-slate-300 disabled:opacity-40"
                    title="Archive session"
                  >
                    Archive
                  </button>
                </div>
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
                  <div
                    onClick={() => setActive(s.id)}
                    className={`group cursor-pointer px-2 py-1.5 rounded flex items-center gap-2 ${
                      activeId === s.id ? "bg-slate-100" : "hover:bg-slate-50"
                    } text-slate-500`}
                  >
                    <span className="h-2 w-2 rounded-full bg-slate-300 shrink-0" />
                    <span className="truncate flex-1">{s.project_title}</span>
                    <button
                      onClick={(e) => onUnarchive(s.id, e)}
                      disabled={busyId === s.id}
                      className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-emerald-700 text-xs px-1.5 py-0.5 rounded hover:bg-white border border-transparent hover:border-slate-300 disabled:opacity-40"
                      title="Restore to active"
                    >
                      Restore
                    </button>
                    <button
                      onClick={(e) => onDelete(s.id, s.project_title, e)}
                      disabled={busyId === s.id}
                      className="opacity-0 group-hover:opacity-100 text-rose-600 hover:text-white hover:bg-rose-600 text-xs px-1.5 py-0.5 rounded border border-transparent hover:border-rose-600 disabled:opacity-40"
                      title="Permanently delete"
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
}
