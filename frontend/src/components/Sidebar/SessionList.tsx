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
    <aside className="flex flex-col border-r border-border bg-surface">
      <div className="border-b border-border p-3.5">
        <button
          onClick={() => setDraft(true)}
          disabled={draft && !activeId}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent py-2 text-sm font-medium text-accent-foreground shadow-sm transition hover:brightness-110 disabled:bg-accent/40"
        >
          <span className="text-base leading-none">＋</span> New Session
        </button>
      </div>
      <div className="flex-1 space-y-5 overflow-y-auto p-3 text-sm">
        <div>
          <h3 className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Active
          </h3>
          <ul className="space-y-0.5">
            {active.length === 0 && (
              <li className="px-2 italic text-muted">No active sessions</li>
            )}
            {active.map((s) => (
              <li key={s.id}>
                <div
                  onClick={() => setActive(s.id)}
                  className={`group relative flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 transition ${
                    activeId === s.id
                      ? "bg-accent/10 text-accent before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-accent"
                      : "hover:bg-surface-muted"
                  }`}
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                  <span className="flex-1 truncate font-medium">{s.project_title}</span>
                  <button
                    onClick={(e) => onArchive(s.id, e)}
                    disabled={busyId === s.id}
                    className="rounded-md border border-border px-1.5 py-0.5 text-[10px] text-muted opacity-0 transition hover:bg-surface hover:text-foreground group-hover:opacity-100 disabled:opacity-40"
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
            <h3 className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
              Archived
            </h3>
            <ul className="space-y-0.5">
              {archived.map((s) => (
                <li key={s.id}>
                  <div
                    onClick={() => setActive(s.id)}
                    className={`group flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 text-muted transition ${
                      activeId === s.id ? "bg-surface-muted" : "hover:bg-surface-muted"
                    }`}
                  >
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-border" />
                    <span className="flex-1 truncate">{s.project_title}</span>
                    <button
                      onClick={(e) => onUnarchive(s.id, e)}
                      disabled={busyId === s.id}
                      className="rounded-md border border-border px-1.5 py-0.5 text-[10px] text-muted opacity-0 transition hover:bg-surface hover:text-success group-hover:opacity-100 disabled:opacity-40"
                      title="Restore to active"
                    >
                      Restore
                    </button>
                    <button
                      onClick={(e) => onDelete(s.id, s.project_title, e)}
                      disabled={busyId === s.id}
                      className="rounded-md border border-transparent px-1.5 py-0.5 text-[10px] text-danger opacity-0 transition hover:bg-danger hover:text-white group-hover:opacity-100 disabled:opacity-40"
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
