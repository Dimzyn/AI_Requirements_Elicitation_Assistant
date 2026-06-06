import { useEffect, useState } from "react";
import { myMemberProjects, type Project } from "../../api/projects";
import { openProjectSession } from "../../api/sessions";
import { useSessionStore } from "../../store/sessionStore";

export default function ProjectSidebar() {
  const { setActive, setSessions } = useSessionStore();
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const ps = await myMemberProjects();
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

  async function open(p: Project) {
    setBusyId(p.id);
    try {
      const session = await openProjectSession(p.id);
      setSessions([session]);
      setActive(session.id);
      setActiveProjectId(p.id);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <aside className="flex flex-col border-r border-border bg-surface">
      <div className="border-b border-border p-3.5">
        <h2 className="text-sm font-semibold text-foreground">Your projects</h2>
      </div>
      <div className="flex-1 space-y-0.5 overflow-y-auto p-3 text-sm">
        {projects.length === 0 && (
          <p className="px-2 italic text-muted">No project invitations yet.</p>
        )}
        {projects.map((p) => (
          <button
            key={p.id}
            onClick={() => open(p)}
            disabled={busyId === p.id}
            className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition disabled:opacity-50 ${
              activeProjectId === p.id
                ? "bg-accent/10 text-accent"
                : "hover:bg-surface-muted text-foreground"
            }`}
          >
            <span className="flex-1 truncate font-medium">{p.title}</span>
          </button>
        ))}
      </div>
    </aside>
  );
}
