# SRE (Requirements Engineer) Role — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Requirements Engineer role who can view all stakeholder sessions, review/edit/prioritize requirements, and curate the final spec — without being interviewed.

**Architecture:** Role field on the user document gates access. JWT token carries the user_id; the backend reads the user's role from DB to decide scope. Frontend decodes role from a `/auth/me` endpoint and renders either the stakeholder chat UI or the SRE spec table.

**Tech Stack:** FastAPI, Motor (MongoDB), React 19, TypeScript, Zustand, Tailwind CSS

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/routers/auth.py` | Add `GET /auth/me` returning user profile with role |
| Modify | `backend/app/schemas/auth.py` | Add `UserProfile` response schema |
| Modify | `backend/app/deps.py` | Add `current_user_doc` dependency that returns full user doc with role |
| Modify | `backend/app/routers/sessions.py` | SRE bypasses `user_id` filter on list |
| Modify | `backend/app/routers/export.py` | SRE bypasses ownership check on requirements list |
| Create | `backend/app/routers/requirements.py` | `GET /requirements` (all, SRE only), `PATCH /requirements/{id}` |
| Modify | `backend/app/schemas/requirement.py` | Add `RequirementPatch`, extend `RequirementOut` with new fields |
| Modify | `backend/app/main.py` | Register new requirements router |
| Modify | `backend/app/db/mongo.py` | Add index on `requirements.status` |
| Modify | `frontend/src/api/auth.ts` | Add `getMe()` call |
| Modify | `frontend/src/store/authStore.ts` | Store role alongside token |
| Modify | `frontend/src/App.tsx` | Add `/spec` route, role-aware redirect |
| Modify | `frontend/src/components/Auth/ProtectedRoute.tsx` | Fetch profile on mount, expose role |
| Create | `frontend/src/pages/SpecPage.tsx` | SRE table UI: sessions tree, requirements table, edit drawer |
| Create | `frontend/src/api/requirements.ts` | API calls for SRE requirement endpoints |
| Create | `frontend/src/store/specStore.ts` | Zustand store for SRE page state |

---

## Task 1: Backend — User role + `/auth/me` endpoint

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/routers/auth.py`
- Modify: `backend/app/deps.py`

- [ ] **Step 1: Add `UserProfile` schema and `role` to signup**

In `backend/app/schemas/auth.py`, add:
```python
class UserProfile(BaseModel):
    id: str
    email: str
    real_name: str
    role: str
```

- [ ] **Step 2: Add `role` field to signup user document**

In `backend/app/routers/auth.py`, add `"role": "stakeholder"` to the signup `doc` dict.

- [ ] **Step 3: Add `GET /auth/me` endpoint**

In `backend/app/routers/auth.py`, add:
```python
from ..deps import current_user_id_from_token
from ..schemas.auth import UserProfile

@router.get("/me", response_model=UserProfile)
async def get_me(user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    return UserProfile(
        id=str(user["_id"]),
        email=user["email"],
        real_name=user["real_name"],
        role=user.get("role", "stakeholder"),
    )
```

- [ ] **Step 4: Add `current_user_doc` dependency**

In `backend/app/deps.py`, add a dependency that returns the full user document (needed later for role checks):
```python
from bson import ObjectId
from .db.mongo import get_db

async def current_user_doc(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = decode_token(authorization.split(" ", 1)[1])
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no subject")
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(sub)})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    user["_id"] = str(user["_id"])
    return user
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/routers/auth.py backend/app/deps.py
git commit -m "feat(auth): add role field to users + GET /auth/me endpoint"
```

---

## Task 2: Backend — SRE sees all sessions

**Files:**
- Modify: `backend/app/routers/sessions.py`

- [ ] **Step 1: Modify `list_sessions` to bypass user_id filter for SRE**

```python
from ..deps import current_user_id_from_token, current_user_doc

@router.get("", response_model=list[SessionOut])
async def list_sessions(user: dict = Depends(current_user_doc)):
    db = get_db()
    query = {} if user.get("role") == "requirements_engineer" else {"user_id": user["_id"]}
    out: list[SessionOut] = []
    async for s in db.sessions.find(query).sort("created_at", -1):
        out.append(_to_out(s))
    return out
```

- [ ] **Step 2: Add `user_id` and `created_at` to `SessionOut` for SRE context**

In `backend/app/schemas/session.py`:
```python
class SessionOut(BaseModel):
    id: str
    project_title: str
    status: str
    phase: str
    user_id: str | None = None
    created_at: str | None = None
```

Update `_to_out` in sessions.py:
```python
def _to_out(doc: dict) -> SessionOut:
    return SessionOut(
        id=str(doc["_id"]),
        project_title=doc["project_title"],
        status=doc["status"],
        phase=doc["phase"],
        user_id=doc.get("user_id"),
        created_at=doc.get("created_at", "").isoformat() if doc.get("created_at") else None,
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/sessions.py backend/app/schemas/session.py
git commit -m "feat(sessions): SRE role sees all sessions across users"
```

---

## Task 3: Backend — Requirement schema expansion + PATCH endpoint

**Files:**
- Modify: `backend/app/schemas/requirement.py`
- Create: `backend/app/routers/requirements.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/db/mongo.py`

- [ ] **Step 1: Extend requirement schemas**

In `backend/app/schemas/requirement.py`:
```python
from datetime import datetime
from pydantic import BaseModel
from typing import Optional


class RequirementOut(BaseModel):
    id: str
    session_id: str
    statement: str
    type: str
    source_turn_id: str
    priority: str | None = None
    status: str | None = None
    acceptance_criteria: str | None = None
    edited_by: str | None = None
    edited_at: str | None = None
    created_at: datetime


class RequirementPatch(BaseModel):
    statement: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    acceptance_criteria: Optional[str] = None
```

- [ ] **Step 2: Create requirements router**

Create `backend/app/routers/requirements.py`:
```python
from bson import ObjectId
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db.mongo import get_db
from ..deps import current_user_doc
from ..schemas.requirement import RequirementOut, RequirementPatch

router = APIRouter(prefix="/requirements", tags=["requirements"])

_VALID_PRIORITIES = {"must", "should", "could", "wont"}
_VALID_STATUSES = {"pending", "approved", "rejected", "needs_clarification"}
_VALID_TYPES = {"functional", "non_functional", "constraint"}


def _to_out(doc: dict) -> RequirementOut:
    return RequirementOut(
        id=str(doc["_id"]),
        session_id=doc["session_id"],
        statement=doc["statement"],
        type=doc["type"],
        source_turn_id=doc.get("source_turn_id", ""),
        priority=doc.get("priority"),
        status=doc.get("status", "pending"),
        acceptance_criteria=doc.get("acceptance_criteria"),
        edited_by=doc.get("edited_by"),
        edited_at=doc["edited_at"].isoformat() if doc.get("edited_at") else None,
        created_at=doc["created_at"],
    )


def _require_sre(user: dict):
    if user.get("role") != "requirements_engineer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires requirements_engineer role")


@router.get("", response_model=list[RequirementOut])
async def list_all_requirements(
    session_id: str | None = Query(default=None),
    req_status: str | None = Query(default=None, alias="status"),
    req_type: str | None = Query(default=None, alias="type"),
    user: dict = Depends(current_user_doc),
):
    _require_sre(user)
    db = get_db()
    query: dict = {}
    if session_id:
        query["session_id"] = session_id
    if req_status:
        query["status"] = req_status
    if req_type:
        query["type"] = req_type
    out: list[RequirementOut] = []
    async for r in db.requirements.find(query).sort("created_at", 1):
        out.append(_to_out(r))
    return out


@router.patch("/{rid}", response_model=RequirementOut)
async def patch_requirement(
    rid: str,
    body: RequirementPatch,
    user: dict = Depends(current_user_doc),
):
    _require_sre(user)
    db = get_db()
    try:
        oid = ObjectId(rid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement not found") from exc

    updates: dict = {}
    if body.statement is not None:
        updates["statement"] = body.statement
    if body.type is not None:
        if body.type not in _VALID_TYPES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"type must be one of {_VALID_TYPES}")
        updates["type"] = body.type
    if body.priority is not None:
        if body.priority not in _VALID_PRIORITIES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"priority must be one of {_VALID_PRIORITIES}")
        updates["priority"] = body.priority
    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"status must be one of {_VALID_STATUSES}")
        updates["status"] = body.status
    if body.acceptance_criteria is not None:
        updates["acceptance_criteria"] = body.acceptance_criteria

    if not updates:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "no fields to update")

    updates["edited_by"] = user["_id"]
    updates["edited_at"] = datetime.utcnow()

    from pymongo import ReturnDocument
    doc = await db.requirements.find_one_and_update(
        {"_id": oid},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "requirement not found")
    return _to_out(doc)
```

- [ ] **Step 3: Register router in main.py**

In `backend/app/main.py`, add:
```python
from .routers import requirements as requirements_router
app.include_router(requirements_router.router)
```

- [ ] **Step 4: Add status index**

In `backend/app/db/mongo.py` inside `init_indexes`:
```python
await db.requirements.create_index("status")
```

- [ ] **Step 5: Update existing `RequirementOut` usage in export router**

In `backend/app/routers/export.py`, update the `list_requirements` function to include `session_id` in the response:
```python
out.append(
    RequirementOut(
        id=str(r["_id"]),
        session_id=r["session_id"],
        statement=r["statement"],
        type=r["type"],
        source_turn_id=r.get("source_turn_id", ""),
        priority=r.get("priority"),
        status=r.get("status", "pending"),
        acceptance_criteria=r.get("acceptance_criteria"),
        edited_by=r.get("edited_by"),
        edited_at=r["edited_at"].isoformat() if r.get("edited_at") else None,
        created_at=r["created_at"],
    )
)
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/requirement.py backend/app/routers/requirements.py backend/app/main.py backend/app/db/mongo.py backend/app/routers/export.py
git commit -m "feat(requirements): SRE PATCH endpoint + list-all with filters"
```

---

## Task 4: Frontend — Auth store with role + `/auth/me`

**Files:**
- Modify: `frontend/src/api/auth.ts`
- Modify: `frontend/src/store/authStore.ts`
- Modify: `frontend/src/components/Auth/ProtectedRoute.tsx`

- [ ] **Step 1: Add `getMe` API call**

In `frontend/src/api/auth.ts`:
```typescript
export type UserProfile = {
  id: string;
  email: string;
  real_name: string;
  role: "stakeholder" | "requirements_engineer";
};

export const getMe = () => api.get<UserProfile>("/auth/me").then((r) => r.data);
```

- [ ] **Step 2: Extend auth store with role**

In `frontend/src/store/authStore.ts`:
```typescript
import { create } from "zustand";
import { persist } from "zustand/middleware";

type AuthState = {
  token: string | null;
  role: "stakeholder" | "requirements_engineer" | null;
  setToken: (token: string | null) => void;
  setRole: (role: "stakeholder" | "requirements_engineer" | null) => void;
  clear: () => void;
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      role: null,
      setToken: (token) => set({ token }),
      setRole: (role) => set({ role }),
      clear: () => set({ token: null, role: null }),
    }),
    { name: "probing-auth" }
  )
);
```

- [ ] **Step 3: Update ProtectedRoute to fetch role on mount**

In `frontend/src/components/Auth/ProtectedRoute.tsx`:
```typescript
import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { getMe } from "../../api/auth";

export default function ProtectedRoute() {
  const token = useAuthStore((s) => s.token);
  const setRole = useAuthStore((s) => s.setRole);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    getMe()
      .then((p) => setRole(p.role))
      .catch(() => useAuthStore.getState().clear())
      .finally(() => setLoading(false));
  }, [token]);

  if (!token) return <Navigate to="/login" replace />;
  if (loading) return <div className="h-screen flex items-center justify-center">Loading...</div>;
  return <Outlet />;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/auth.ts frontend/src/store/authStore.ts frontend/src/components/Auth/ProtectedRoute.tsx
git commit -m "feat(frontend): store user role from /auth/me on login"
```

---

## Task 5: Frontend — Role-aware routing

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add role-based redirect and /spec route**

```typescript
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import MainPage from "./pages/MainPage";
import SpecPage from "./pages/SpecPage";
import ProtectedRoute from "./components/Auth/ProtectedRoute";
import { useAuthStore } from "./store/authStore";

function RoleRedirect() {
  const role = useAuthStore((s) => s.role);
  if (role === "requirements_engineer") return <Navigate to="/spec" replace />;
  return <Navigate to="/chat" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<RoleRedirect />} />
          <Route path="/chat" element={<MainPage />} />
          <Route path="/spec" element={<SpecPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(routing): role-aware redirect — stakeholder→/chat, SRE→/spec"
```

---

## Task 6: Frontend — SRE API layer + store

**Files:**
- Create: `frontend/src/api/requirements.ts`
- Create: `frontend/src/store/specStore.ts`

- [ ] **Step 1: Create requirements API module**

Create `frontend/src/api/requirements.ts`:
```typescript
import { api } from "./client";

export type SreRequirement = {
  id: string;
  session_id: string;
  statement: string;
  type: "functional" | "non_functional" | "constraint";
  source_turn_id: string;
  priority: string | null;
  status: string | null;
  acceptance_criteria: string | null;
  edited_by: string | null;
  edited_at: string | null;
  created_at: string;
};

export type RequirementPatch = {
  statement?: string;
  type?: string;
  priority?: string;
  status?: string;
  acceptance_criteria?: string;
};

export const listAllRequirements = (params?: {
  session_id?: string;
  status?: string;
  type?: string;
}) => api.get<SreRequirement[]>("/requirements", { params }).then((r) => r.data);

export const patchRequirement = (id: string, body: RequirementPatch) =>
  api.patch<SreRequirement>(`/requirements/${id}`, body).then((r) => r.data);
```

- [ ] **Step 2: Create spec store**

Create `frontend/src/store/specStore.ts`:
```typescript
import { create } from "zustand";
import type { SreRequirement } from "../api/requirements";
import type { Session } from "../api/sessions";

type SpecState = {
  sessions: Session[];
  setSessions: (s: Session[]) => void;
  requirements: SreRequirement[];
  setRequirements: (r: SreRequirement[]) => void;
  updateRequirement: (r: SreRequirement) => void;
  selectedId: string | null;
  setSelectedId: (id: string | null) => void;
  filterSessionId: string | null;
  setFilterSessionId: (id: string | null) => void;
  filterStatus: string | null;
  setFilterStatus: (s: string | null) => void;
  filterType: string | null;
  setFilterType: (t: string | null) => void;
};

export const useSpecStore = create<SpecState>((set) => ({
  sessions: [],
  setSessions: (sessions) => set({ sessions }),
  requirements: [],
  setRequirements: (requirements) => set({ requirements }),
  updateRequirement: (updated) =>
    set((s) => ({
      requirements: s.requirements.map((r) => (r.id === updated.id ? updated : r)),
    })),
  selectedId: null,
  setSelectedId: (selectedId) => set({ selectedId }),
  filterSessionId: null,
  setFilterSessionId: (filterSessionId) => set({ filterSessionId }),
  filterStatus: null,
  setFilterStatus: (filterStatus) => set({ filterStatus }),
  filterType: null,
  setFilterType: (filterType) => set({ filterType }),
}));
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/requirements.ts frontend/src/store/specStore.ts
git commit -m "feat(sre): API layer + Zustand store for spec page"
```

---

## Task 7: Frontend — SpecPage (SRE table UI)

**Files:**
- Create: `frontend/src/pages/SpecPage.tsx`

- [ ] **Step 1: Build the full SpecPage component**

Create `frontend/src/pages/SpecPage.tsx`:
```tsx
import { useEffect, useState } from "react";
import { useAuthStore } from "../store/authStore";
import { useSpecStore } from "../store/specStore";
import { listSessions } from "../api/sessions";
import { listAllRequirements, patchRequirement } from "../api/requirements";
import type { RequirementPatch, SreRequirement } from "../api/requirements";
import { useNavigate } from "react-router-dom";

const TYPE_OPTIONS = ["functional", "non_functional", "constraint"] as const;
const PRIORITY_OPTIONS = ["must", "should", "could", "wont"] as const;
const STATUS_OPTIONS = ["pending", "approved", "rejected", "needs_clarification"] as const;

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
    sessions, setSessions,
    requirements, setRequirements, updateRequirement,
    selectedId, setSelectedId,
    filterSessionId, setFilterSessionId,
    filterStatus, setFilterStatus,
    filterType, setFilterType,
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
    } catch { /* toast could go here */ }
    setSaving(false);
  };

  return (
    <div className="h-screen grid grid-rows-[auto_1fr] bg-slate-50">
      <header className="bg-white border-b px-4 py-2 flex items-center justify-between">
        <h1 className="font-semibold text-slate-800">Requirements Spec — Curator View</h1>
        <button
          onClick={() => { clear(); nav("/login"); }}
          className="text-sm px-3 py-1 border rounded hover:bg-slate-100"
        >
          Log out
        </button>
      </header>

      <div className="grid grid-cols-[220px_1fr] overflow-hidden">
        {/* Left rail — sessions tree */}
        <aside className="border-r bg-white p-3 overflow-y-auto">
          <h2 className="text-xs uppercase tracking-wider text-slate-500 mb-2">Sessions</h2>
          <button
            onClick={() => setFilterSessionId(null)}
            className={`block w-full text-left text-sm px-2 py-1 rounded mb-1 ${
              !filterSessionId ? "bg-indigo-100 text-indigo-800" : "hover:bg-slate-100"
            }`}
          >
            All sessions
          </button>
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => setFilterSessionId(s.id)}
              className={`block w-full text-left text-sm px-2 py-1 rounded mb-1 truncate ${
                filterSessionId === s.id ? "bg-indigo-100 text-indigo-800" : "hover:bg-slate-100"
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
                {TYPE_OPTIONS.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
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
                {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
              </select>
            </label>
            <span className="ml-auto text-slate-500">{requirements.length} requirements</span>
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
                      selectedId === r.id ? "bg-indigo-50" : "hover:bg-slate-50"
                    }`}
                  >
                    <td className="px-3 py-2 text-slate-400">{i + 1}</td>
                    <td className="px-3 py-2">{r.statement}</td>
                    <td className="px-3 py-2">{TYPE_LABEL[r.type] ?? r.type}</td>
                    <td className="px-3 py-2">{r.priority ? PRIORITY_LABEL[r.priority] ?? r.priority : "—"}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        r.status === "approved" ? "bg-green-100 text-green-800" :
                        r.status === "rejected" ? "bg-red-100 text-red-800" :
                        r.status === "needs_clarification" ? "bg-amber-100 text-amber-800" :
                        "bg-slate-100 text-slate-600"
                      }`}>
                        {STATUS_LABEL[r.status ?? "pending"] ?? "Pending"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {requirements.length === 0 && (
              <p className="text-center text-slate-400 mt-8">No requirements match filters.</p>
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
        <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-lg leading-none">&times;</button>
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
          <select value={type} onChange={(e) => setType(e.target.value)} className="block border rounded px-2 py-1 mt-0.5 text-sm">
            {TYPE_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="text-xs text-slate-500">
          Priority
          <select value={priority} onChange={(e) => setPriority(e.target.value)} className="block border rounded px-2 py-1 mt-0.5 text-sm">
            <option value="">—</option>
            {PRIORITY_OPTIONS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
      </div>
      <div className="grid grid-cols-[auto_1fr] gap-2 items-end">
        <label className="text-xs text-slate-500">
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="block border rounded px-2 py-1 mt-0.5 text-sm">
            {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/SpecPage.tsx
git commit -m "feat(sre): SpecPage — requirements table with filters + edit drawer"
```

---

## Task 8: Backend — SRE can read any session's turns + requirements

**Files:**
- Modify: `backend/app/routers/export.py`
- Modify: `backend/app/routers/dialogue.py`

- [ ] **Step 1: Allow SRE to list requirements for any session**

In `backend/app/routers/export.py`, update `list_requirements`:
```python
from ..deps import current_user_id_from_token, current_user_doc

@router.get("/{sid}/requirements", response_model=list[RequirementOut])
async def list_requirements(
    sid: str,
    user: dict = Depends(current_user_doc),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    if user.get("role") == "requirements_engineer":
        s = await db.sessions.find_one({"_id": oid})
    else:
        s = await db.sessions.find_one({"_id": oid, "user_id": user["_id"]})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")

    out: list[RequirementOut] = []
    async for r in db.requirements.find({"session_id": sid}).sort("created_at", 1):
        out.append(_to_out_req(r))
    return out
```

- [ ] **Step 2: Allow SRE to list turns for any session**

In `backend/app/routers/dialogue.py`, update `list_turns`:
```python
from ..deps import current_user_id_from_token, current_user_doc

@router.get("/{sid}/turns", response_model=list[TurnOut])
async def list_turns(
    sid: str,
    user: dict = Depends(current_user_doc),
):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    if user.get("role") == "requirements_engineer":
        session = await db.sessions.find_one({"_id": oid})
    else:
        session = await db.sessions.find_one({"_id": oid, "user_id": user["_id"]})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    ...
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/export.py backend/app/routers/dialogue.py
git commit -m "feat(auth): SRE can read turns + requirements from any session"
```

---

## Task 9: Manual promotion script

**Files:**
- Create: `backend/scripts/promote_user.py`

- [ ] **Step 1: Write the promotion script**

Create `backend/scripts/promote_user.py`:
```python
"""Promote a user to requirements_engineer role.

Usage:
    python -m scripts.promote_user sre@example.com
"""
import asyncio
import sys
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = "mongodb://mongo:27017"
DB_NAME = "probing"


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.promote_user <email>")
        sys.exit(1)
    email = sys.argv[1]
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    result = await db.users.update_one(
        {"email": email},
        {"$set": {"role": "requirements_engineer"}},
    )
    if result.matched_count == 0:
        print(f"No user found with email: {email}")
        sys.exit(1)
    print(f"Promoted {email} to requirements_engineer")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/promote_user.py
git commit -m "feat(admin): script to promote user to requirements_engineer role"
```

---

## Summary

After all 9 tasks:
- Stakeholders sign up as usual (role defaults to `stakeholder`)
- Admin promotes an account via `python -m scripts.promote_user sre@example.com`
- SRE logs in → auto-redirected to `/spec`
- SRE sees all sessions in left rail, filterable requirements table in center
- SRE can edit statement, type, priority, status, and acceptance criteria
- Stakeholder experience is unchanged — still `/chat` with the AI agent
