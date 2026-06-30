import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSpecStore } from "../store/specStore";
import { listAllSessions } from "../api/sessions";
import { getProject, listProjectSessions, exportProjectSrs } from "../api/projects";
import { listAllRequirements, patchRequirement } from "../api/requirements";
import type { RequirementPatch, SreRequirement } from "../api/requirements";
import { listConflicts, type Conflict } from "../api/conflicts";
import { conflictsByRequirementId } from "../components/Conflicts/conflictMap";
import AppHeader from "../components/AppHeader";
import Badge, { type BadgeTone } from "../components/ui/Badge";

const TYPE_OPTIONS = ["functional", "non_functional", "constraint"] as const;
const PRIORITY_OPTIONS = ["must", "should", "could", "wont"] as const;
const STATUS_OPTIONS = [
  "pending",
  "approved",
  "rejected",
  "needs_clarification",
] as const;

const TYPE_LABEL: Record<string, string> = {
  functional: "FN",
  non_functional: "NFR",
  constraint: "CON",
};
const PRIORITY_LABEL: Record<string, string> = {
  must: "M",
  should: "S",
  could: "C",
  wont: "W",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  needs_clarification: "Clarify",
};

const STATUS_TONE: Record<string, BadgeTone> = {
  approved: "success",
  rejected: "danger",
  needs_clarification: "warning",
  pending: "neutral",
};

// How often to poll for new stakeholder activity (sessions + requirements)
// so the RE sees updates without reloading the browser.
const POLL_MS = 6000;

export default function SpecPage() {
  const {
    sessions,
    setSessions,
    requirements,
    setRequirements,
    updateRequirement,
    selectedId,
    setSelectedId,
    filterSessionId,
    setFilterSessionId,
    filterStatus,
    setFilterStatus,
    filterType,
    setFilterType,
  } = useSpecStore();

  const { id: projectId } = useParams();
  const [saving, setSaving] = useState(false);
  const [projectTitle, setProjectTitle] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);

  const loadSessions = useCallback(() => {
    const req = projectId ? listProjectSessions(projectId) : listAllSessions();
    req.then((s) => setSessions(s)).catch(() => {});
  }, [projectId, setSessions]);

  // Conflicts are project-scoped, so the global curator view (no project) has none.
  const loadConflicts = useCallback(() => {
    if (!projectId) {
      setConflicts([]);
      return;
    }
    listConflicts(projectId, "open").then(setConflicts).catch(() => {});
  }, [projectId]);

  // Map every conflicted requirement id to its conflict so a row can flag itself.
  const conflictByReqId = useMemo(() => conflictsByRequirementId(conflicts), [conflicts]);

  const loadRequirements = useCallback(() => {
    const params: Record<string, string> = {};
    if (projectId) params.project_id = projectId;
    if (filterSessionId) params.session_id = filterSessionId;
    if (filterStatus) params.status = filterStatus;
    if (filterType) params.type = filterType;
    listAllRequirements(params).then(setRequirements).catch(() => {});
  }, [projectId, filterSessionId, filterStatus, filterType, setRequirements]);

  // Reset the session filter when switching projects so a stale selection from
  // another project doesn't hide everything.
  useEffect(() => {
    setFilterSessionId(null);
  }, [projectId, setFilterSessionId]);

  useEffect(() => {
    if (!projectId) return;
    let active = true;
    getProject(projectId)
      .then((p) => {
        if (active) setProjectTitle(p.title);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [projectId]);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    loadRequirements();
  }, [loadRequirements]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional fetch-on-mount; loadConflicts populates the panel
    loadConflicts();
  }, [loadConflicts]);

  // Poll for live updates while the tab is visible. The edit drawer keeps its
  // own local state, so a background refetch won't clobber an in-progress edit.
  useEffect(() => {
    const id = setInterval(() => {
      if (document.hidden) return;
      loadSessions();
      loadRequirements();
      loadConflicts();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [loadSessions, loadRequirements, loadConflicts]);

  const selected = requirements.find((r) => r.id === selectedId) ?? null;

  const onExportSrs = async (format: "md" | "txt" | "pdf") => {
    if (!projectId) return;
    const blob = await exportProjectSrs(projectId, format);
    const base = (projectTitle ?? "requirements").replace(/\s+/g, "_");
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${base}_SRS.${format}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const onSave = async (patch: RequirementPatch) => {
    if (!selected) return;
    setSaving(true);
    try {
      const updated = await patchRequirement(selected.id, patch);
      updateRequirement(updated);
    } catch {
      /* ignore */
    }
    setSaving(false);
  };

  return (
    <div className="grid h-screen grid-rows-[auto_1fr] bg-background">
      <AppHeader
        title={
          projectId && projectTitle
            ? `Requirements — ${projectTitle}`
            : "Requirements Spec — Curator View"
        }
      />

      <div className="grid grid-cols-[220px_1fr] overflow-hidden">
        {/* Left rail — sessions tree */}
        <aside className="overflow-y-auto border-r border-border bg-surface p-3">
          {projectId && (
            <Link
              to={`/projects/${projectId}`}
              className="mb-3 inline-flex items-center gap-1 px-1 text-xs text-muted transition hover:text-foreground hover:underline"
            >
              ← Back to project
            </Link>
          )}
          <h2 className="mb-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
            Sessions
          </h2>
          <button
            onClick={() => setFilterSessionId(null)}
            className={`mb-1 block w-full rounded-lg px-2.5 py-1.5 text-left text-sm transition ${
              !filterSessionId
                ? "bg-accent/10 font-medium text-accent"
                : "text-foreground hover:bg-surface-muted"
            }`}
          >
            All sessions
          </button>
          {sessions.map((s) => {
            const name =
              s.stakeholder_name || s.stakeholder_email || "Unknown stakeholder";
            return (
              <button
                key={s.id}
                onClick={() => setFilterSessionId(s.id)}
                className={`mb-1 block w-full rounded-lg px-2.5 py-1.5 text-left transition ${
                  filterSessionId === s.id
                    ? "bg-accent/10 text-accent"
                    : "text-foreground hover:bg-surface-muted"
                }`}
                title={name}
              >
                <span
                  className={`block truncate text-sm ${
                    filterSessionId === s.id ? "font-medium" : ""
                  }`}
                >
                  {name}
                </span>
              </button>
            );
          })}
        </aside>

        {/* Main content */}
        <div className="flex flex-col overflow-hidden">
          <div className="flex items-center gap-3 border-b border-border bg-surface px-4 py-2.5 text-sm">
            <label className="flex items-center gap-1.5 text-muted">
              Type
              <select
                value={filterType ?? ""}
                onChange={(e) => setFilterType(e.target.value || null)}
                className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
              >
                <option value="">All</option>
                {TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABEL[t]}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1.5 text-muted">
              Status
              <select
                value={filterStatus ?? ""}
                onChange={(e) => setFilterStatus(e.target.value || null)}
                className="rounded-md border border-border bg-surface px-2 py-1 text-foreground"
              >
                <option value="">All</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </label>
            <div className="ml-auto flex items-center gap-3">
              <span className="text-muted">{requirements.length} requirements</span>
              {projectId && (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => onExportSrs("pdf")}
                    title="Download the Software Requirements Specification as a PDF"
                    className="rounded-lg bg-accent px-3 py-1.5 text-xs font-semibold text-accent-foreground shadow-sm transition hover:brightness-110"
                  >
                    ⬇ Export SRS (PDF)
                  </button>
                  <button
                    onClick={() => onExportSrs("md")}
                    title="Download as editable Markdown"
                    className="rounded-md border border-border px-2 py-1.5 text-xs text-muted transition hover:bg-surface-muted hover:text-foreground"
                  >
                    .md
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-surface-muted text-left text-muted">
                <tr>
                  <th className="w-16 px-3 py-2 font-medium">#</th>
                  <th className="px-3 py-2 font-medium">Statement</th>
                  <th className="w-16 px-3 py-2 font-medium">Type</th>
                  <th className="w-16 px-3 py-2 font-medium">Pri</th>
                  <th className="w-24 px-3 py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {requirements.map((r, i) => {
                  const conflict = conflictByReqId.get(r.id);
                  return (
                  <tr
                    key={r.id}
                    onClick={() => setSelectedId(r.id)}
                    className={`cursor-pointer border-b border-border transition ${
                      selectedId === r.id
                        ? "bg-accent/10"
                        : conflict
                        ? "bg-warning/10 hover:bg-warning/15"
                        : "hover:bg-surface-muted"
                    }`}
                  >
                    <td className="px-3 py-2 text-muted">{i + 1}</td>
                    <td className="px-3 py-2 text-foreground">
                      <div className="flex items-center gap-2">
                        <span>{r.statement}</span>
                        {conflict && projectId && (
                          <Link
                            to={`/projects/${projectId}`}
                            onClick={(e) => e.stopPropagation()}
                            title={conflict.explanation}
                            className="shrink-0"
                          >
                            <Badge tone="warning">⚠ Conflict</Badge>
                          </Link>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-foreground">{TYPE_LABEL[r.type] ?? r.type}</td>
                    <td className="px-3 py-2 text-foreground">
                      {r.priority ? (PRIORITY_LABEL[r.priority] ?? r.priority) : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={STATUS_TONE[r.status ?? "pending"] ?? "neutral"}>
                        {STATUS_LABEL[r.status ?? "pending"] ?? "Pending"}
                      </Badge>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
            {requirements.length === 0 && (
              <p className="mt-8 text-center text-muted">No requirements match filters.</p>
            )}
          </div>

          {selected && (
            <EditDrawer
              key={selected.id}
              requirement={selected}
              saving={saving}
              onSave={onSave}
              onClose={() => setSelectedId(null)}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function EditDrawer({
  requirement: r,
  saving,
  onSave,
  onClose,
}: {
  requirement: SreRequirement;
  saving: boolean;
  onSave: (patch: RequirementPatch) => void;
  onClose: () => void;
}) {
  const [statement, setStatement] = useState(r.statement);
  const [type, setType] = useState<string>(r.type);
  const [priority, setPriority] = useState(r.priority ?? "");
  const [status, setStatus] = useState(r.status ?? "pending");
  const [ac, setAc] = useState(r.acceptance_criteria ?? "");

  const dirty =
    statement !== r.statement ||
    type !== r.type ||
    priority !== (r.priority ?? "") ||
    status !== (r.status ?? "pending") ||
    ac !== (r.acceptance_criteria ?? "");

  const handleSave = () => {
    const patch: RequirementPatch = {};
    if (statement !== r.statement) patch.statement = statement;
    if (type !== r.type) patch.type = type;
    if (priority !== (r.priority ?? "")) patch.priority = priority;
    if (status !== (r.status ?? "pending")) patch.status = status;
    if (ac !== (r.acceptance_criteria ?? "")) patch.acceptance_criteria = ac;
    onSave(patch);
  };

  return (
    <div className="space-y-2.5 border-t border-border bg-surface px-4 py-3.5 shadow-lift">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">Edit Requirement</h3>
        <button
          onClick={onClose}
          className="text-lg leading-none text-muted transition hover:text-foreground"
        >
          &times;
        </button>
      </div>
      <div className="grid grid-cols-[1fr_auto_auto] items-end gap-2.5">
        <label className="text-xs text-muted">
          Statement
          <input
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            className="mt-1 block w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          />
        </label>
        <label className="text-xs text-muted">
          Type
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="mt-1 block rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground"
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-muted">
          Priority
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="mt-1 block rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground"
          >
            <option value="">—</option>
            {PRIORITY_OPTIONS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="grid grid-cols-[auto_1fr] items-end gap-2.5">
        <label className="text-xs text-muted">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="mt-1 block rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-muted">
          Acceptance Criteria
          <input
            value={ac}
            onChange={(e) => setAc(e.target.value)}
            placeholder="Given… When… Then…"
            className="mt-1 block w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted/70 focus:border-ring focus:outline-none focus:ring-2 focus:ring-ring/20"
          />
        </label>
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-accent-foreground shadow-sm transition hover:brightness-110 disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
