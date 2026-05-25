import { useEffect, useState } from "react";
import { useAuthStore } from "../store/authStore";
import { useSpecStore } from "../store/specStore";
import { listSessions } from "../api/sessions";
import { listAllRequirements, patchRequirement } from "../api/requirements";
import type { RequirementPatch, SreRequirement } from "../api/requirements";
import { useNavigate } from "react-router-dom";

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

export default function SpecPage() {
  const clear = useAuthStore((s) => s.clear);
  const nav = useNavigate();
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

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listSessions().then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    const params: Record<string, string> = {};
    if (filterSessionId) params.session_id = filterSessionId;
    if (filterStatus) params.status = filterStatus;
    if (filterType) params.type = filterType;
    listAllRequirements(params).then(setRequirements).catch(() => {});
  }, [filterSessionId, filterStatus, filterType]);

  const selected = requirements.find((r) => r.id === selectedId) ?? null;

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
    <div className="h-screen grid grid-rows-[auto_1fr] bg-slate-50">
      <header className="bg-white border-b px-4 py-2 flex items-center justify-between">
        <h1 className="font-semibold text-slate-800">
          Requirements Spec — Curator View
        </h1>
        <button
          onClick={() => {
            clear();
            nav("/login");
          }}
          className="text-sm px-3 py-1 border rounded hover:bg-slate-100"
        >
          Log out
        </button>
      </header>

      <div className="grid grid-cols-[220px_1fr] overflow-hidden">
        {/* Left rail — sessions tree */}
        <aside className="border-r bg-white p-3 overflow-y-auto">
          <h2 className="text-xs uppercase tracking-wider text-slate-500 mb-2">
            Sessions
          </h2>
          <button
            onClick={() => setFilterSessionId(null)}
            className={`block w-full text-left text-sm px-2 py-1 rounded mb-1 ${
              !filterSessionId
                ? "bg-indigo-100 text-indigo-800"
                : "hover:bg-slate-100"
            }`}
          >
            All sessions
          </button>
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setFilterSessionId(s.id)}
              className={`block w-full text-left text-sm px-2 py-1 rounded mb-1 truncate ${
                filterSessionId === s.id
                  ? "bg-indigo-100 text-indigo-800"
                  : "hover:bg-slate-100"
              }`}
              title={s.project_title}
            >
              {s.project_title}
            </button>
          ))}
        </aside>

        {/* Main content */}
        <div className="flex flex-col overflow-hidden">
          {/* Filter bar */}
          <div className="bg-white border-b px-4 py-2 flex gap-3 items-center text-sm">
            <label className="flex items-center gap-1">
              Type:
              <select
                value={filterType ?? ""}
                onChange={(e) => setFilterType(e.target.value || null)}
                className="border rounded px-2 py-1"
              >
                <option value="">All</option>
                {TYPE_OPTIONS.map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABEL[t]}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1">
              Status:
              <select
                value={filterStatus ?? ""}
                onChange={(e) => setFilterStatus(e.target.value || null)}
                className="border rounded px-2 py-1"
              >
                <option value="">All</option>
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABEL[s]}
                  </option>
                ))}
              </select>
            </label>
            <span className="ml-auto text-slate-500">
              {requirements.length} requirements
            </span>
          </div>

          {/* Table */}
          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-100 text-left">
                <tr>
                  <th className="px-3 py-2 w-16">#</th>
                  <th className="px-3 py-2">Statement</th>
                  <th className="px-3 py-2 w-16">Type</th>
                  <th className="px-3 py-2 w-16">Pri</th>
                  <th className="px-3 py-2 w-24">Status</th>
                </tr>
              </thead>
              <tbody>
                {requirements.map((r, i) => (
                  <tr
                    key={r.id}
                    onClick={() => setSelectedId(r.id)}
                    className={`cursor-pointer border-b ${
                      selectedId === r.id
                        ? "bg-indigo-50"
                        : "hover:bg-slate-50"
                    }`}
                  >
                    <td className="px-3 py-2 text-slate-400">{i + 1}</td>
                    <td className="px-3 py-2">{r.statement}</td>
                    <td className="px-3 py-2">
                      {TYPE_LABEL[r.type] ?? r.type}
                    </td>
                    <td className="px-3 py-2">
                      {r.priority
                        ? (PRIORITY_LABEL[r.priority] ?? r.priority)
                        : "—"}
                    </td>
                    <td className="px-3 py-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full ${
                          r.status === "approved"
                            ? "bg-green-100 text-green-800"
                            : r.status === "rejected"
                              ? "bg-red-100 text-red-800"
                              : r.status === "needs_clarification"
                                ? "bg-amber-100 text-amber-800"
                                : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {STATUS_LABEL[r.status ?? "pending"] ?? "Pending"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {requirements.length === 0 && (
              <p className="text-center text-slate-400 mt-8">
                No requirements match filters.
              </p>
            )}
          </div>

          {/* Detail drawer */}
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
  const [type, setType] = useState(r.type);
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
    <div className="border-t bg-white px-4 py-3 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-sm">Edit Requirement</h3>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-600 text-lg leading-none"
        >
          &times;
        </button>
      </div>
      <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
        <label className="text-xs text-slate-500">
          Statement
          <input
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
            className="block w-full border rounded px-2 py-1 mt-0.5 text-sm"
          />
        </label>
        <label className="text-xs text-slate-500">
          Type
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="block border rounded px-2 py-1 mt-0.5 text-sm"
          >
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-500">
          Priority
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className="block border rounded px-2 py-1 mt-0.5 text-sm"
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
      <div className="grid grid-cols-[auto_1fr] gap-2 items-end">
        <label className="text-xs text-slate-500">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="block border rounded px-2 py-1 mt-0.5 text-sm"
          >
            {STATUS_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-slate-500">
          Acceptance Criteria
          <input
            value={ac}
            onChange={(e) => setAc(e.target.value)}
            placeholder="Given… When… Then…"
            className="block w-full border rounded px-2 py-1 mt-0.5 text-sm"
          />
        </label>
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className="px-3 py-1 bg-indigo-600 text-white text-sm rounded disabled:opacity-40 hover:bg-indigo-700"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
