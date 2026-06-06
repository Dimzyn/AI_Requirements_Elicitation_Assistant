import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects, createProject, type Project } from "../api/projects";
import AppHeader from "../components/AppHeader";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [title, setTitle] = useState("");
  const [background, setBackground] = useState("");
  const [creating, setCreating] = useState(false);

  async function refresh() {
    listProjects().then(setProjects).catch(() => {});
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setCreating(true);
    try {
      await createProject({ title: title.trim(), background: background.trim() || undefined });
      setTitle("");
      setBackground("");
      refresh();
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader title="Projects" />

      <div className="overflow-y-auto">
        <div className="max-w-3xl mx-auto p-6 space-y-6">
          {/* Create form */}
          <section className="rounded-xl border border-border bg-surface p-4 shadow-card space-y-3">
            <h2 className="text-sm font-semibold text-foreground">New project</h2>
            <form onSubmit={onCreate} className="space-y-2">
              <input
                className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
                placeholder="Project title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
              <textarea
                className="w-full rounded-lg border border-border bg-surface px-3 py-2.5 text-sm text-foreground transition placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20 resize-none"
                placeholder="Background / goals / scope (context for the AI)"
                rows={3}
                value={background}
                onChange={(e) => setBackground(e.target.value)}
              />
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={creating || !title.trim()}
                  className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground shadow-sm transition hover:brightness-110 disabled:opacity-40"
                >
                  {creating ? "Creating…" : "Create project"}
                </button>
              </div>
            </form>
          </section>

          {/* Project list */}
          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted px-1">
              Your projects ({projects.length})
            </h2>
            {projects.length === 0 && (
              <p className="text-sm text-muted py-4 text-center">
                No projects yet. Create one above.
              </p>
            )}
            <ul className="space-y-2">
              {projects.map((p) => (
                <li
                  key={p.id}
                  className="rounded-lg border border-border bg-surface p-4 shadow-card transition hover:bg-surface-muted"
                >
                  <Link
                    to={`/projects/${p.id}`}
                    className="font-medium text-foreground hover:text-accent hover:underline"
                  >
                    {p.title}
                  </Link>
                  {p.background && (
                    <p className="mt-1 text-xs text-muted line-clamp-2">{p.background}</p>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
