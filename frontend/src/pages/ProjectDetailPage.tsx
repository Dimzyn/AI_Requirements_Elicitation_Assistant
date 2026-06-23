import { useCallback, useEffect, useMemo, useState } from "react";
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
import { listConflicts, type Conflict } from "../api/conflicts";
import AppHeader from "../components/AppHeader";
import Badge from "../components/ui/Badge";
import ConflictsPanel from "../components/Conflicts/ConflictsPanel";

// Poll so new interview sessions and status changes appear without a reload.
const POLL_MS = 6000;

export default function ProjectDetailPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [sessions, setSessions] = useState<ProjectSession[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [email, setEmail] = useState("");
  const [lastInvite, setLastInvite] = useState<Invite | null>(null);
  const [inviting, setInviting] = useState(false);
  const [completingId, setCompletingId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [p, m, s, c] = await Promise.all([
        getProject(id),
        listMembers(id),
        listProjectSessions(id),
        listConflicts(id).catch(() => [] as Conflict[]),
      ]);
      setProject(p);
      setMembers(m);
      setSessions(s);
      setConflicts(c);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  }, [id]);

  // Split real interviews from the auto-created conflict-resolution chats, and map
  // each conflict id to its conflict so a resolution chat can show what it's about.
  const interviews = useMemo(
    () => sessions.filter((s) => s.kind !== "conflict_resolution"),
    [sessions]
  );
  const resolutionChats = useMemo(
    () => sessions.filter((s) => s.kind === "conflict_resolution"),
    [sessions]
  );
  const conflictById = useMemo(() => {
    const m = new Map<string, Conflict>();
    for (const c of conflicts) m.set(c.id, c);
    return m;
  }, [conflicts]);

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

          {/* Interview sessions */}
          <section className="space-y-2">
            <div className="flex items-center justify-between px-1">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
                Interview sessions ({interviews.length})
              </h2>
              <Link
                to={`/projects/${id}/spec`}
                className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition hover:bg-surface-muted"
              >
                View all requirements
              </Link>
            </div>
            {interviews.length === 0 ? (
              <p className="text-sm text-muted py-2 text-center">
                No sessions yet. Sessions are created when a stakeholder starts a chat.
              </p>
            ) : (
              <ul className="space-y-2">
                {interviews.map((s) => (
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
                        {s.stakeholder_finished && s.status !== "completed" && (
                          <Badge tone="info" className="ml-2">
                            Ready for review
                          </Badge>
                        )}
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

          {/* Conflict-resolution chats — AI-opened, one per stakeholder behind a conflict */}
          {resolutionChats.length > 0 && (
            <section className="space-y-2">
              <h2 className="px-1 text-sm font-semibold uppercase tracking-wider text-muted">
                Conflict-resolution chats ({resolutionChats.length})
              </h2>
              <ul className="space-y-2">
                {resolutionChats.map((s) => {
                  const c = s.conflict_id ? conflictById.get(s.conflict_id) : undefined;
                  const full = c
                    ? `${c.requirement_a.statement} ⇄ ${c.requirement_b.statement}`
                    : undefined;
                  return (
                    <li
                      key={s.id}
                      className="rounded-lg border border-warning/30 bg-warning/5 px-4 py-3 shadow-card"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="warning">⚠ Conflict resolution</Badge>
                        <Link
                          to={`/chat?session=${s.id}`}
                          className="text-sm font-medium text-foreground hover:text-accent hover:underline"
                        >
                          {s.stakeholder_name || s.stakeholder_email || "Unknown stakeholder"}
                        </Link>
                        <span className="text-xs text-muted">· {s.status}</span>
                      </div>
                      <p className="mt-1 truncate text-xs text-muted" title={full}>
                        {c ? (
                          <>
                            Re: <span className="text-foreground">“{c.requirement_a.statement}”</span>{" "}
                            ⇄ <span className="text-foreground">“{c.requirement_b.statement}”</span>
                          </>
                        ) : (
                          "Resolving a requirement conflict."
                        )}
                      </p>
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
