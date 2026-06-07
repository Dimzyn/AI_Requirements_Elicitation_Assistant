import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  getProject,
  inviteStakeholder,
  listMembers,
  listProjectSessions,
  completeSession,
  type Project,
  type Member,
  type Invite,
  type ProjectSession,
} from "../api/projects";
import AppHeader from "../components/AppHeader";
import ConflictsPanel from "../components/Conflicts/ConflictsPanel";

// Poll so new interview sessions and status changes appear without a reload.
const POLL_MS = 6000;

export default function ProjectDetailPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [sessions, setSessions] = useState<ProjectSession[]>([]);
  const [email, setEmail] = useState("");
  const [lastInvite, setLastInvite] = useState<Invite | null>(null);
  const [inviting, setInviting] = useState(false);
  const [completingId, setCompletingId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [p, m, s] = await Promise.all([
        getProject(id),
        listMembers(id),
        listProjectSessions(id),
      ]);
      setProject(p);
      setMembers(m);
      setSessions(s);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [id]);

  useEffect(() => {
    void (async () => {
      await refresh();
    })();
  }, [refresh]);

  // Poll so new interview sessions and status changes appear without a reload.
  useEffect(() => {
    const intervalId = setInterval(() => {
      if (!document.hidden) refresh();
    }, POLL_MS);
    return () => clearInterval(intervalId);
  }, [refresh]);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setInviting(true);
    try {
      const inv = await inviteStakeholder(id, email.trim());
      setLastInvite(inv);
      setEmail("");
      refresh();
    } finally {
      setInviting(false);
    }
  }

  async function onComplete(sid: string) {
    setCompletingId(sid);
    try {
      await completeSession(sid);
      refresh();
    } finally {
      setCompletingId(null);
    }
  }

  if (!project)
    return (
      <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
        <AppHeader title="Project" />
        <div className="grid place-items-center">
          <p className="text-sm text-muted">
            {loadError ? "Couldn't load this project." : "Loading…"}
          </p>
        </div>
      </div>
    );

  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader title={project.title} />

      <div className="overflow-y-auto">
        <div className="max-w-3xl mx-auto p-6 space-y-6">
          {/* Back nav */}
          <Link to="/projects" className="inline-flex items-center gap-1 text-sm text-muted hover:text-foreground hover:underline">
            ← Projects
          </Link>

          {/* Project header */}
          <div>
            <h1 className="text-xl font-semibold text-foreground">{project.title}</h1>
            {project.background && (
              <p className="mt-2 text-sm text-muted whitespace-pre-wrap">{project.background}</p>
            )}
          </div>

          {/* Invite section */}
          <section className="rounded-xl border border-border bg-surface p-4 shadow-card space-y-3">
            <h2 className="text-sm font-semibold text-foreground">Invite a stakeholder</h2>
            <form onSubmit={onInvite} className="flex gap-2">
              <input
                className="flex-1 rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                type="email"
                placeholder="stakeholder@email.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <button
                type="submit"
                disabled={inviting || !email.trim()}
                className="rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground shadow-sm transition hover:brightness-110 disabled:opacity-40"
              >
                {inviting ? "Sending…" : "Invite"}
              </button>
            </form>
            {lastInvite && (
              <div className="space-y-1 rounded-lg border border-border bg-background px-3 py-2.5 text-sm">
                <p className="text-muted">
                  Share this link with{" "}
                  <span className="font-medium text-foreground">{lastInvite.email}</span>:
                </p>
                <code className="block break-all rounded bg-surface-muted px-2 py-1 text-xs text-foreground">
                  {lastInvite.accept_url}
                </code>
              </div>
            )}
          </section>

          {/* Members section */}
          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted px-1">
              Members ({members.length})
            </h2>
            {members.length === 0 ? (
              <p className="text-sm text-muted py-2 text-center">No members yet.</p>
            ) : (
              <ul className="space-y-1">
                {members.map((m) => (
                  <li
                    key={m.user_id}
                    className="flex items-center gap-3 rounded-lg border border-border bg-surface px-4 py-2.5"
                  >
                    <span className="grid h-7 w-7 place-items-center rounded-full bg-accent/10 text-xs font-semibold text-accent">
                      {m.real_name.charAt(0).toUpperCase()}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-foreground">{m.real_name}</p>
                      <p className="text-xs text-muted">{m.email}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Conflicts section */}
          <ConflictsPanel projectId={id} projectTitle={project.title} />

          {/* Sessions section */}
          <section className="space-y-2">
            <div className="flex items-center justify-between px-1">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
                Interview sessions ({sessions.length})
              </h2>
              <Link
                to={`/projects/${id}/spec`}
                className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted"
              >
                View all requirements
              </Link>
            </div>
            {sessions.length === 0 ? (
              <p className="text-sm text-muted py-2 text-center">
                No sessions yet. Sessions are created when a stakeholder starts a chat.
              </p>
            ) : (
              <ul className="space-y-2">
                {sessions.map((s) => (
                  <li
                    key={s.id}
                    className="flex items-center justify-between rounded-lg border border-border bg-surface px-4 py-3 shadow-card"
                  >
                    <div className="flex-1 min-w-0">
                      <div>
                        <Link
                          to={`/chat?session=${s.id}`}
                          className="text-sm font-medium text-foreground hover:text-accent hover:underline"
                        >
                          {s.stakeholder_name || s.stakeholder_email || "Unknown stakeholder"}
                        </Link>
                        <span
                          className={`ml-2 text-xs ${
                            s.status === "completed" ? "text-success" : "text-muted"
                          }`}
                        >
                          · {s.status}
                        </span>
                      </div>
                      {s.stakeholder_name && s.stakeholder_email && (
                        <p className="mt-0.5 text-xs text-muted truncate">{s.stakeholder_email}</p>
                      )}
                    </div>
                    {s.status !== "completed" && (
                      <button
                        onClick={() => onComplete(s.id)}
                        disabled={completingId === s.id}
                        className="ml-3 shrink-0 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted disabled:opacity-40"
                      >
                        {completingId === s.id ? "Ending…" : "Mark ended"}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
