import { useEffect, useState } from "react";
import { myMemberProjects, type Project } from "../../api/projects";
import { openProjectSession, listSessions, type Session } from "../../api/sessions";
import { useSessionStore } from "../../store/sessionStore";

// Refresh sessions periodically so a conflict-resolution chat the engineer just
// triggered shows up for the stakeholder without a manual reload.
const POLL_MS = 8000;

export default function ProjectSidebar() {
  const { setActive, setSessions, activeId } = useSessionStore();
  const [projects, setProjects] = useState<Project[]>([]);
  const [mySessions, setMySessions] = useState<Session[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  // Fetch all of the stakeholder's sessions and mirror them into the store so the
  // input box can read the active session's status (interview or resolution chat).
  const loadSessions = async (): Promise<Session[]> => {
    try {
      const ss = await listSessions();
      setMySessions(ss);
      setSessions(ss);
      return ss;
    } catch {
      return [];
    }
  };

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [ps] = await Promise.all([myMemberProjects(), loadSessions()]);
        if (!active) return;
        setProjects(ps);
        // Auto-open when the stakeholder belongs to exactly one project.
        if (ps.length === 1) await open(ps[0]);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const id = setInterval(() => {
      if (!document.hidden) void loadSessions();
    }, POLL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function open(p: Project) {
    setBusyId(p.id);
    try {
      const session = await openProjectSession(p.id);
      await loadSessions(); // refresh to include a newly-created interview session
      setActive(session.id);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <aside className="flex flex-col border-r border-border bg-surface">
      <div className="border-b border-border p-3.5">
        <h2 className="text-sm font-semibold text-foreground">Your projects</h2>
      </div>
      <div className="flex-1 space-y-1 overflow-y-auto p-3 text-sm">
        {projects.length === 0 && (
          <p className="px-2 italic text-muted">No project invitations yet.</p>
        )}
        {projects.map((p) => {
          const interview = mySessions.find(
            (s) => s.project_id === p.id && s.kind !== "conflict_resolution"
          );
          const resolutions = mySessions.filter(
            (s) => s.project_id === p.id && s.kind === "conflict_resolution"
          );
          const projectActive =
            !!activeId &&
            (interview?.id === activeId || resolutions.some((r) => r.id === activeId));
          return (
            <div key={p.id} className="space-y-0.5">
              <button
                onClick={() => open(p)}
                disabled={busyId === p.id}
                className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition disabled:opacity-50 ${
                  projectActive ? "bg-accent/10 text-accent" : "hover:bg-surface-muted text-foreground"
                }`}
              >
                <span className="flex-1 truncate font-medium">{p.title}</span>
              </button>
              {resolutions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setActive(s.id)}
                  title="AI-opened chat to resolve a requirement conflict"
                  className={`flex w-full items-center gap-2 rounded-lg py-1.5 pl-6 pr-2.5 text-left text-xs transition ${
                    activeId === s.id ? "bg-warning/15 text-warning" : "text-muted hover:bg-surface-muted"
                  }`}
                >
                  <span aria-hidden>⚠</span>
                  <span className="flex-1 truncate">Resolve conflict</span>
                </button>
              ))}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
