# Multi-Stakeholder Projects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-owner session model with project-scoped collaboration: a Requirements Engineer (RE) owns projects, invites stakeholders by email, and each invited stakeholder runs their own interview inside the shared project; the RE reviews all sessions in projects they own.

**Architecture:** Add three MongoDB collections — `projects`, `memberships`, `invitations` — plus role-aware authorization. Sessions move from `user_id` (single owner) to `project_id` + `stakeholder_id`. The RE's visibility narrows from "all sessions globally" to "sessions in projects I own". Invitations are token-based (no email service in this phase — the link is shown in the RE UI). Frontend adds a public invite-accept page, an RE project-management surface, and a stakeholder project picker.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, Motor (async MongoDB); React 18 + Vite + TypeScript, Zustand, React Router 6, Axios; Pytest + httpx + mongomock-motor (backend), Vitest (frontend).

**Reference spec:** `docs/superpowers/specs/2026-06-04-multi-stakeholder-projects-design.md`

---

## File Structure & Responsibilities

| File | Responsibility |
|---|---|
| `backend/app/models/project.py` | `Project` Pydantic model (owner_id, title, background, goals, scope) |
| `backend/app/models/membership.py` | `Membership` model (project_id, user_id, role_in_project) |
| `backend/app/models/invitation.py` | `Invitation` model + `InvitationStatus` enum |
| `backend/app/models/user.py` | (modify) add `role`, `status` fields to align model with DB |
| `backend/app/models/session.py` | (modify) `user_id` → `stakeholder_id`, add `project_id` |
| `backend/app/db/mongo.py` | (modify) indexes for projects/memberships/invitations + session reshape |
| `backend/app/deps.py` | (modify) add `require_engineer` / `require_stakeholder` dependencies |
| `backend/app/services/invite_service.py` | token generation + invitation lifecycle helpers |
| `backend/app/schemas/project.py` | request/response models for projects, members, invitations |
| `backend/app/schemas/invitation.py` | invite-accept request/response models |
| `backend/app/routers/projects.py` | RE: create/list/get projects, invite, list members, list sessions |
| `backend/app/routers/invitations.py` | public: view + accept invitation (sets password, joins project) |
| `backend/app/routers/sessions.py` | (modify) project-scoped ownership; RE sees owned-project sessions |
| `backend/app/routers/dialogue.py` | (modify) ownership checks use `stakeholder_id`; RE access via project owner |
| `backend/app/main.py` | (modify) mount projects + invitations routers |
| `frontend/src/api/projects.ts` | project + member + invitation API client |
| `frontend/src/api/invitations.ts` | public invite-accept API client |
| `frontend/src/pages/InviteAcceptPage.tsx` | public page: set password, join project |
| `frontend/src/pages/ProjectsPage.tsx` | RE: list/create projects |
| `frontend/src/pages/ProjectDetailPage.tsx` | RE: project background, invite form, member + session list |
| `frontend/src/pages/MainPage.tsx` | (modify) stakeholder picks project → own session; "ended" banner |
| `frontend/src/App.tsx` | (modify) routes for `/projects`, `/projects/:id`, `/invite/:token` |

---

## Conventions (read before starting)

- IDs are stored as Mongo `ObjectId` and returned to clients as `str`.
- All timestamps are timezone-aware UTC: `datetime.now(timezone.utc)`.
- Tests use the existing `backend/tests/conftest.py` fixture that patches `app.db.mongo._client` with `AsyncMongoMockClient`. Integration tests use `AsyncClient(transport=ASGITransport(app=app), base_url="http://t")`.
- Role values are exactly `"requirements_engineer"` and `"stakeholder"` (already used across the codebase).
- A stakeholder has **at most one** session per project (`(project_id, stakeholder_id)` unique).
- Run backend tests from `backend/`: `pytest -q`. Run frontend tests from `frontend/`: `npm run test`.

---

## Phase 1 — Data Models & Indexes

### Task 1.1: `Project` model

**Files:**
- Create: `backend/app/models/project.py`
- Test: `backend/tests/test_project_model.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_project_model.py`:
```python
from app.models.project import Project


def test_project_defaults_and_required():
    p = Project(owner_id="re1", title="Hospital System")
    assert p.owner_id == "re1"
    assert p.title == "Hospital System"
    assert p.background is None
    assert p.created_at == p.updated_at or p.created_at <= p.updated_at


def test_project_accepts_optional_context():
    p = Project(owner_id="re1", title="X", background="b", goals="g", scope="s")
    assert (p.background, p.goals, p.scope) == ("b", "g", "s")
```

- [ ] **Step 2: Run test, confirm failure**

Run: `cd backend && pytest tests/test_project_model.py -v`
Expected: ImportError (no module `app.models.project`).

- [ ] **Step 3: Implement model**

`backend/app/models/project.py`:
```python
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Project(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    owner_id: str
    title: str
    background: Optional[str] = None
    goals: Optional[str] = None
    scope: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Run test, confirm pass**

Run: `pytest tests/test_project_model.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/project.py backend/tests/test_project_model.py
git commit -m "feat(models): add Project model"
```

### Task 1.2: `Membership` model

**Files:**
- Create: `backend/app/models/membership.py`
- Test: `backend/tests/test_membership_model.py`

- [ ] **Step 1: Write failing test**

```python
from app.models.membership import Membership


def test_membership_defaults():
    m = Membership(project_id="p1", user_id="u1")
    assert m.project_id == "p1"
    assert m.user_id == "u1"
    assert m.role_in_project == "stakeholder"
    assert m.joined_at is not None
```

- [ ] **Step 2: Run, confirm failure** — `pytest tests/test_membership_model.py -v` → ImportError.

- [ ] **Step 3: Implement**

`backend/app/models/membership.py`:
```python
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Membership(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    user_id: str
    role_in_project: str = "stakeholder"
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/membership.py backend/tests/test_membership_model.py
git commit -m "feat(models): add Membership model"
```

### Task 1.3: `Invitation` model

**Files:**
- Create: `backend/app/models/invitation.py`
- Test: `backend/tests/test_invitation_model.py`

- [ ] **Step 1: Write failing test**

```python
from datetime import datetime, timezone
from app.models.invitation import Invitation, InvitationStatus


def test_invitation_defaults_pending_and_future_expiry():
    inv = Invitation(project_id="p1", email="s@x.com", token="tok123")
    assert inv.status == InvitationStatus.PENDING
    assert inv.expires_at > datetime.now(timezone.utc)


def test_invitation_status_enum_values():
    assert InvitationStatus.PENDING == "pending"
    assert InvitationStatus.ACCEPTED == "accepted"
    assert InvitationStatus.EXPIRED == "expired"
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Implement**

`backend/app/models/invitation.py`:
```python
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


def _default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=7)


class Invitation(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    email: EmailStr
    token: str
    status: InvitationStatus = InvitationStatus.PENDING
    expires_at: datetime = Field(default_factory=_default_expiry)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/invitation.py backend/tests/test_invitation_model.py
git commit -m "feat(models): add Invitation model + status enum"
```

### Task 1.4: Extend `User` model; reshape `InterviewSession`

**Files:**
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/session.py`
- Test: `backend/tests/test_models_roles.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_models_roles.py`:
```python
from app.models.user import User
from app.models.session import InterviewSession, SessionStatus


def test_user_role_status_defaults():
    u = User(email="a@x.com", hashed_password="h", real_name="A")
    assert u.role == "stakeholder"
    assert u.status == "active"


def test_session_is_project_scoped():
    s = InterviewSession(project_id="p1", stakeholder_id="u1")
    assert s.project_id == "p1"
    assert s.stakeholder_id == "u1"
    assert s.status == SessionStatus.ACTIVE
```

- [ ] **Step 2: Run, confirm failure** — `pytest tests/test_models_roles.py -v` (TypeError: unexpected/ missing fields).

- [ ] **Step 3: Modify `models/user.py`** — add `role` and `status` after `domain_level`:

```python
    domain_level: str = "novice"  # novice|intermediate|expert
    role: str = "stakeholder"  # stakeholder | requirements_engineer
    status: str = "active"  # active | invited
```

- [ ] **Step 4: Modify `models/session.py`** — replace `user_id` and `project_title`:

```python
class InterviewSession(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    stakeholder_id: str
    title: Optional[str] = None  # conversation label, auto-named from first message
    status: SessionStatus = SessionStatus.ACTIVE
    phase: str = "exploration"  # exploration|deepening|validation
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

> Note: `project_title` (old single-owner label) is replaced by `title`. The RE-set project name now lives on `Project.title`. Routers in Phase 5 are updated to match.

- [ ] **Step 5: Run, confirm pass.**

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/user.py backend/app/models/session.py backend/tests/test_models_roles.py
git commit -m "feat(models): user role/status + project-scoped session"
```

### Task 1.5: Indexes for new collections

**Files:**
- Modify: `backend/app/db/mongo.py`
- Test: `backend/tests/test_indexes.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_indexes.py`:
```python
import pytest
from app.db.mongo import init_indexes, get_db


@pytest.mark.asyncio
async def test_init_indexes_creates_new_collections():
    await init_indexes()
    db = get_db()
    member_idx = await db.memberships.index_information()
    invite_idx = await db.invitations.index_information()
    # unique compound on membership, unique token on invitation
    assert any(v.get("unique") for v in member_idx.values())
    assert any(v.get("unique") for v in invite_idx.values())
```

- [ ] **Step 2: Run, confirm failure** — `pytest tests/test_indexes.py -v`.

- [ ] **Step 3: Modify `init_indexes` in `db/mongo.py`** — replace the sessions index line and append new ones:

```python
async def init_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.sessions.create_index([("project_id", 1), ("stakeholder_id", 1)], unique=True)
    await db.sessions.create_index([("stakeholder_id", 1), ("status", 1)])
    await db.turns.create_index([("session_id", 1), ("created_at", 1)])
    await db.requirements.create_index("session_id")
    await db.requirements.create_index("status")
    await db.projects.create_index("owner_id")
    await db.memberships.create_index([("project_id", 1), ("user_id", 1)], unique=True)
    await db.invitations.create_index("token", unique=True)
    await db.invitations.create_index([("project_id", 1), ("email", 1)])
```

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/mongo.py backend/tests/test_indexes.py
git commit -m "feat(db): indexes for projects/memberships/invitations + project-scoped sessions"
```

---

## Phase 2 — Role Authorization Dependencies

### Task 2.1: `require_engineer` and `require_stakeholder`

**Files:**
- Modify: `backend/app/deps.py`
- Test: `backend/tests/test_role_deps.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_role_deps.py`:
```python
import pytest
from fastapi import HTTPException
from app.deps import require_engineer, require_stakeholder


@pytest.mark.asyncio
async def test_require_engineer_allows_re():
    user = {"_id": "u1", "role": "requirements_engineer"}
    assert await require_engineer(user=user) is user


@pytest.mark.asyncio
async def test_require_engineer_rejects_stakeholder():
    with pytest.raises(HTTPException) as exc:
        await require_engineer(user={"_id": "u1", "role": "stakeholder"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_stakeholder_rejects_re():
    with pytest.raises(HTTPException) as exc:
        await require_stakeholder(user={"_id": "u1", "role": "requirements_engineer"})
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Append to `backend/app/deps.py`**

```python
from fastapi import Depends


async def require_engineer(user: dict = Depends(current_user_doc)) -> dict:
    if user.get("role") != "requirements_engineer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires requirements_engineer role")
    return user


async def require_stakeholder(user: dict = Depends(current_user_doc)) -> dict:
    if user.get("role") != "stakeholder":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires stakeholder role")
    return user
```

> The unit test calls these with `user=` directly (bypassing `Depends`), which works because `Depends(...)` is only resolved by FastAPI at request time; in a direct call the passed kwarg is used.

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/deps.py backend/tests/test_role_deps.py
git commit -m "feat(auth): role-gated dependencies require_engineer/require_stakeholder"
```

---

## Phase 3 — Projects Router (RE)

### Task 3.1: Project schemas

**Files:**
- Create: `backend/app/schemas/project.py`

- [ ] **Step 1: Create schemas (no test needed; exercised by router tests)**

`backend/app/schemas/project.py`:
```python
from typing import Optional

from pydantic import BaseModel, EmailStr


class ProjectCreate(BaseModel):
    title: str
    background: Optional[str] = None
    goals: Optional[str] = None
    scope: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    title: str
    background: Optional[str] = None
    goals: Optional[str] = None
    scope: Optional[str] = None
    created_at: Optional[str] = None


class MemberOut(BaseModel):
    user_id: str
    email: str
    real_name: str
    joined_at: Optional[str] = None


class InviteCreate(BaseModel):
    email: EmailStr


class InviteOut(BaseModel):
    id: str
    email: str
    status: str
    token: str
    accept_url: str  # FYP: shown in RE UI for manual sharing
    expires_at: Optional[str] = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/project.py
git commit -m "feat(schemas): project/member/invite schemas"
```

### Task 3.2: `invite_service` token helper

**Files:**
- Create: `backend/app/services/invite_service.py`
- Test: `backend/tests/test_invite_service.py`

- [ ] **Step 1: Write failing test**

```python
from app.services.invite_service import new_token, accept_url_for


def test_new_token_is_unique_and_urlsafe():
    a, b = new_token(), new_token()
    assert a != b
    assert len(a) >= 20
    assert "/" not in a and "+" not in a


def test_accept_url_contains_token():
    url = accept_url_for("abc123", base="http://localhost:5173")
    assert url == "http://localhost:5173/invite/abc123"
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Implement**

`backend/app/services/invite_service.py`:
```python
import secrets

from ..config import settings


def new_token() -> str:
    return secrets.token_urlsafe(32)


def accept_url_for(token: str, base: str | None = None) -> str:
    origin = base or settings.cors_origins.split(",")[0].strip()
    return f"{origin}/invite/{token}"
```

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/invite_service.py backend/tests/test_invite_service.py
git commit -m "feat(invite): token + accept-url helpers"
```

### Task 3.3: Projects router — create / list / get

**Files:**
- Create: `backend/app/routers/projects.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_projects_router.py`

- [ ] **Step 1: Write failing integration test**

`backend/tests/test_projects_router.py`:
```python
import pytest
from bson import ObjectId
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_token(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    # promote to RE directly in the mock db
    db = get_db()
    await db.users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    return (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]


@pytest.mark.asyncio
async def test_re_creates_and_lists_own_projects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        tok = await _re_token(c)
        h = {"Authorization": f"Bearer {tok}"}
        r = await c.post("/projects", json={"title": "Hospital", "background": "b"}, headers=h)
        assert r.status_code == 201
        pid = r.json()["id"]
        r = await c.get("/projects", headers=h)
        assert [p["id"] for p in r.json()] == [pid]


@pytest.mark.asyncio
async def test_stakeholder_cannot_create_project():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/auth/signup", json={"email": "s@x.com", "password": "Passw0rd!", "real_name": "S"})
        tok = (await c.post("/auth/login", json={"email": "s@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.post("/projects", json={"title": "X"}, headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403
```

- [ ] **Step 2: Run, confirm failure** — 404 (router not mounted).

- [ ] **Step 3: Implement router (create/list/get only for now)**

`backend/app/routers/projects.py`:
```python
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from ..db.mongo import get_db
from ..deps import require_engineer
from ..schemas.project import ProjectCreate, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_out(doc: dict) -> ProjectOut:
    return ProjectOut(
        id=str(doc["_id"]),
        title=doc["title"],
        background=doc.get("background"),
        goals=doc.get("goals"),
        scope=doc.get("scope"),
        created_at=doc["created_at"].isoformat() if doc.get("created_at") else None,
    )


async def _owned_project_or_404(db, pid: str, owner_id: str) -> dict:
    try:
        oid = ObjectId(pid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found") from exc
    doc = await db.projects.find_one({"_id": oid, "owner_id": owner_id})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return doc


@router.post("", status_code=201, response_model=ProjectOut)
async def create_project(body: ProjectCreate, user: dict = Depends(require_engineer)):
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = {
        "owner_id": user["_id"],
        "title": body.title.strip() or "Untitled Project",
        "background": body.background,
        "goals": body.goals,
        "scope": body.scope,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.projects.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _project_out(doc)


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: dict = Depends(require_engineer)):
    db = get_db()
    out: list[ProjectOut] = []
    async for p in db.projects.find({"owner_id": user["_id"]}).sort("created_at", -1):
        out.append(_project_out(p))
    return out


@router.get("/{pid}", response_model=ProjectOut)
async def get_project(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    doc = await _owned_project_or_404(db, pid, user["_id"])
    return _project_out(doc)
```

- [ ] **Step 4: Mount in `backend/app/main.py`**

Add with the other `include_router` lines:
```python
from .routers import projects as projects_router
app.include_router(projects_router.router)
```

- [ ] **Step 5: Run, confirm pass** — `pytest tests/test_projects_router.py -v`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/projects.py backend/app/main.py backend/tests/test_projects_router.py
git commit -m "feat(projects): RE create/list/get projects (role-gated, owner-scoped)"
```

---

## Phase 4 — Invitations & Membership

### Task 4.1: Create invitation (RE) + list members

**Files:**
- Modify: `backend/app/routers/projects.py`
- Test: `backend/tests/test_invitations_create.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_invitations_create.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_token(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    return (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]


@pytest.mark.asyncio
async def test_re_invites_stakeholder_returns_accept_url():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h = {"Authorization": f"Bearer {await _re_token(c)}"}
        pid = (await c.post("/projects", json={"title": "P"}, headers=h)).json()["id"]
        r = await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "pending"
        assert body["token"] in body["accept_url"]
        assert body["accept_url"].endswith(f"/invite/{body['token']}")
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Add to `backend/app/routers/projects.py`**

Add imports and endpoints:
```python
from ..schemas.project import InviteCreate, InviteOut, MemberOut
from ..models.invitation import InvitationStatus
from ..services.invite_service import new_token, accept_url_for


@router.post("/{pid}/invitations", status_code=201, response_model=InviteOut)
async def invite_stakeholder(pid: str, body: InviteCreate, user: dict = Depends(require_engineer)):
    db = get_db()
    await _owned_project_or_404(db, pid, user["_id"])
    token = new_token()
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    doc = {
        "project_id": pid,
        "email": str(body.email),
        "token": token,
        "status": InvitationStatus.PENDING.value,
        "expires_at": now + timedelta(days=7),
        "created_at": now,
    }
    res = await db.invitations.insert_one(doc)
    return InviteOut(
        id=str(res.inserted_id),
        email=doc["email"],
        status=doc["status"],
        token=token,
        accept_url=accept_url_for(token),
        expires_at=doc["expires_at"].isoformat(),
    )


@router.get("/{pid}/members", response_model=list[MemberOut])
async def list_members(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    await _owned_project_or_404(db, pid, user["_id"])
    out: list[MemberOut] = []
    async for m in db.memberships.find({"project_id": pid}):
        u = await db.users.find_one({"_id": __import__("bson").ObjectId(m["user_id"])})
        if not u:
            continue
        out.append(MemberOut(
            user_id=m["user_id"],
            email=u["email"],
            real_name=u["real_name"],
            joined_at=m["joined_at"].isoformat() if m.get("joined_at") else None,
        ))
    return out
```

> Cleaner: add `from bson import ObjectId` to the top of the file and use `ObjectId(m["user_id"])` instead of the inline `__import__`. Do that.

- [ ] **Step 4: Run, confirm pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/projects.py backend/tests/test_invitations_create.py
git commit -m "feat(invite): RE creates invitation + lists members"
```

### Task 4.2: View + accept invitation (public)

**Files:**
- Create: `backend/app/schemas/invitation.py`
- Create: `backend/app/routers/invitations.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_invitation_accept.py`

- [ ] **Step 1: Write failing test (new user path + existing user path + expiry)**

`backend/tests/test_invitation_accept.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_and_project(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    tok = (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    pid = (await c.post("/projects", json={"title": "P"}, headers=h)).json()["id"]
    return h, pid


@pytest.mark.asyncio
async def test_view_then_accept_creates_user_and_membership():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]

        r = await c.get(f"/invitations/{token}")
        assert r.status_code == 200
        assert r.json()["email"] == "s@x.com"
        assert r.json()["project_title"] == "P"

        r = await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "Stan"})
        assert r.status_code == 200
        assert "access_token" in r.json()

        db = get_db()
        u = await db.users.find_one({"email": "s@x.com"})
        assert u["role"] == "stakeholder"
        assert await db.memberships.find_one({"project_id": pid, "user_id": str(u["_id"])})
        inv = await db.invitations.find_one({"token": token})
        assert inv["status"] == "accepted"


@pytest.mark.asyncio
async def test_accept_twice_is_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]
        await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "Stan"})
        r = await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "Stan"})
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_expired_invitation_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        h, pid = await _re_and_project(c)
        token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=h)).json()["token"]
        await get_db().invitations.update_one(
            {"token": token},
            {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(days=1)}},
        )
        r = await c.get(f"/invitations/{token}")
        assert r.status_code == 410
```

- [ ] **Step 2: Run, confirm failure.**

- [ ] **Step 3: Create `backend/app/schemas/invitation.py`**

```python
from typing import Optional

from pydantic import BaseModel, Field


class InvitationView(BaseModel):
    email: str
    project_title: str
    status: str


class AcceptRequest(BaseModel):
    password: str = Field(min_length=8)
    real_name: Optional[str] = None


class AcceptResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [ ] **Step 4: Create `backend/app/routers/invitations.py`**

```python
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status

from ..db.mongo import get_db
from ..models.invitation import InvitationStatus
from ..schemas.invitation import InvitationView, AcceptRequest, AcceptResponse
from ..services.auth_service import hash_password, create_token

router = APIRouter(prefix="/invitations", tags=["invitations"])


async def _load_active_invitation(db, token: str) -> dict:
    inv = await db.invitations.find_one({"token": token})
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation not found")
    if inv["status"] == InvitationStatus.ACCEPTED.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "invitation already accepted")
    expires_at = inv["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        await db.invitations.update_one({"_id": inv["_id"]}, {"$set": {"status": InvitationStatus.EXPIRED.value}})
        raise HTTPException(status.HTTP_410_GONE, "invitation expired")
    return inv


@router.get("/{token}", response_model=InvitationView)
async def view_invitation(token: str):
    db = get_db()
    inv = await _load_active_invitation(db, token)
    project = await db.projects.find_one({"_id": ObjectId(inv["project_id"])})
    return InvitationView(
        email=inv["email"],
        project_title=project["title"] if project else "(unknown project)",
        status=inv["status"],
    )


@router.post("/{token}/accept", response_model=AcceptResponse)
async def accept_invitation(token: str, body: AcceptRequest):
    db = get_db()
    inv = await _load_active_invitation(db, token)

    user = await db.users.find_one({"email": inv["email"]})
    if user:
        user_id = str(user["_id"])
    else:
        now = datetime.now(timezone.utc)
        doc = {
            "email": inv["email"],
            "hashed_password": hash_password(body.password),
            "real_name": body.real_name or inv["email"].split("@")[0],
            "phone": None,
            "domain_level": "novice",
            "role": "stakeholder",
            "status": "active",
            "created_at": now,
        }
        res = await db.users.insert_one(doc)
        user_id = str(res.inserted_id)

    # idempotent membership (unique index protects against duplicates)
    existing = await db.memberships.find_one({"project_id": inv["project_id"], "user_id": user_id})
    if not existing:
        await db.memberships.insert_one({
            "project_id": inv["project_id"],
            "user_id": user_id,
            "role_in_project": "stakeholder",
            "joined_at": datetime.now(timezone.utc),
        })

    await db.invitations.update_one({"_id": inv["_id"]}, {"$set": {"status": InvitationStatus.ACCEPTED.value}})
    return AcceptResponse(access_token=create_token({"sub": user_id}))
```

- [ ] **Step 5: Mount in `backend/app/main.py`**

```python
from .routers import invitations as invitations_router
app.include_router(invitations_router.router)
```

- [ ] **Step 6: Run, confirm pass** — `pytest tests/test_invitation_accept.py -v`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/invitation.py backend/app/routers/invitations.py backend/app/main.py backend/tests/test_invitation_accept.py
git commit -m "feat(invite): public view + accept invitation (creates user + membership)"
```

---

## Phase 5 — Session Migration to Project Scope

### Task 5.1: Stakeholder get-or-create session in a project

**Files:**
- Modify: `backend/app/schemas/session.py`
- Modify: `backend/app/routers/sessions.py`
- Test: `backend/tests/test_sessions_project_scope.py`

- [ ] **Step 1: Inspect current `schemas/session.py`**

Run: `pytest -q` first to confirm a green baseline before editing. Then open `backend/app/schemas/session.py` and note the `SessionOut` shape (it currently exposes `project_title`, `user_id`).

- [ ] **Step 2: Write failing test**

`backend/tests/test_sessions_project_scope.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.mongo import get_db


async def _re_project_and_invited_stakeholder(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    re_tok = (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]
    reh = {"Authorization": f"Bearer {re_tok}"}
    pid = (await c.post("/projects", json={"title": "P"}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "S"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    return reh, sh, pid


@pytest.mark.asyncio
async def test_stakeholder_get_or_create_single_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        r1 = await c.post(f"/projects/{pid}/session", headers=sh)
        assert r1.status_code in (200, 201)
        sid = r1.json()["id"]
        r2 = await c.post(f"/projects/{pid}/session", headers=sh)
        assert r2.json()["id"] == sid  # idempotent: one session per (project, stakeholder)


@pytest.mark.asyncio
async def test_non_member_cannot_open_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        await c.post("/auth/signup", json={"email": "out@x.com", "password": "Passw0rd!", "real_name": "O"})
        out_tok = (await c.post("/auth/login", json={"email": "out@x.com", "password": "Passw0rd!"})).json()["access_token"]
        r = await c.post(f"/projects/{pid}/session", headers={"Authorization": f"Bearer {out_tok}"})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_re_lists_sessions_in_owned_project():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        await c.post(f"/projects/{pid}/session", headers=sh)
        r = await c.get(f"/projects/{pid}/sessions", headers=reh)
        assert r.status_code == 200
        assert len(r.json()) == 1
```

- [ ] **Step 3: Update `backend/app/schemas/session.py`**

Replace `SessionOut` so it is project-scoped (keep `SessionCreate` if present, unused fields removed):
```python
from typing import Optional

from pydantic import BaseModel


class SessionOut(BaseModel):
    id: str
    project_id: str
    stakeholder_id: str
    title: Optional[str] = None
    status: str
    phase: str
    created_at: Optional[str] = None
```

- [ ] **Step 4: Rewrite `backend/app/routers/sessions.py`**

Replace the file with project-scoped ownership. Key changes: `_to_out` uses new fields; add membership helpers; add `POST /projects/{pid}/session` (stakeholder get-or-create) and `GET /projects/{pid}/sessions` (RE list); `GET /sessions` returns the caller's own sessions (stakeholder); archive/unarchive/delete now match on `stakeholder_id`.

```python
from bson import ObjectId
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import ReturnDocument

from ..db.mongo import get_db
from ..deps import current_user_doc, require_engineer, require_stakeholder
from ..schemas.session import SessionOut

router = APIRouter(tags=["sessions"])

GREETING = (
    "Hi! I'm here to help capture what you'd like to build. "
    "What's the project or idea you have in mind?"
)


def _to_out(doc: dict) -> SessionOut:
    return SessionOut(
        id=str(doc["_id"]),
        project_id=doc["project_id"],
        stakeholder_id=doc["stakeholder_id"],
        title=doc.get("title"),
        status=doc["status"],
        phase=doc["phase"],
        created_at=doc["created_at"].isoformat() if doc.get("created_at") else None,
    )


async def _is_member(db, project_id: str, user_id: str) -> bool:
    return bool(await db.memberships.find_one({"project_id": project_id, "user_id": user_id}))


async def _owned_project_or_404(db, pid: str, owner_id: str) -> dict:
    try:
        oid = ObjectId(pid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found") from exc
    doc = await db.projects.find_one({"_id": oid, "owner_id": owner_id})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return doc


@router.post("/projects/{pid}/session", response_model=SessionOut)
async def open_my_session(pid: str, user: dict = Depends(require_stakeholder)):
    db = get_db()
    if not await _is_member(db, pid, user["_id"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not a member of this project")
    existing = await db.sessions.find_one({"project_id": pid, "stakeholder_id": user["_id"]})
    if existing:
        return _to_out(existing)
    now = datetime.now(timezone.utc)
    doc = {
        "project_id": pid,
        "stakeholder_id": user["_id"],
        "title": None,
        "status": "active",
        "phase": "exploration",
        "summary": None,
        "auto_named": False,
        "created_at": now,
        "updated_at": now,
    }
    res = await db.sessions.insert_one(doc)
    doc["_id"] = res.inserted_id
    await db.turns.insert_one({
        "session_id": str(res.inserted_id),
        "role": "agent",
        "content": GREETING,
        "created_at": now,
    })
    return _to_out(doc)


@router.get("/projects/{pid}/sessions", response_model=list[SessionOut])
async def list_project_sessions(pid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    await _owned_project_or_404(db, pid, user["_id"])
    out: list[SessionOut] = []
    async for s in db.sessions.find({"project_id": pid}).sort("created_at", -1):
        out.append(_to_out(s))
    return out


@router.get("/sessions", response_model=list[SessionOut])
async def list_my_sessions(user: dict = Depends(current_user_doc)):
    db = get_db()
    out: list[SessionOut] = []
    async for s in db.sessions.find({"stakeholder_id": user["_id"]}).sort("created_at", -1):
        out.append(_to_out(s))
    return out


@router.post("/sessions/{sid}/complete", response_model=SessionOut)
async def complete_session(sid: str, user: dict = Depends(require_engineer)):
    db = get_db()
    try:
        oid = ObjectId(sid)
    except Exception as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found") from exc
    s = await db.sessions.find_one({"_id": oid})
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    await _owned_project_or_404(db, s["project_id"], user["_id"])
    s = await db.sessions.find_one_and_update(
        {"_id": oid},
        {"$set": {"status": "completed", "updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    return _to_out(s)
```

> The old `archive`/`unarchive`/`delete` endpoints are dropped from the stakeholder flow for this phase (a stakeholder now has exactly one session per project). If they are still imported elsewhere, remove those imports. The "ended" state is represented by `status == "completed"`, set by the RE via `/sessions/{sid}/complete`.

- [ ] **Step 5: Run, confirm pass** — `pytest tests/test_sessions_project_scope.py -v`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/sessions.py backend/app/schemas/session.py backend/tests/test_sessions_project_scope.py
git commit -m "feat(sessions): project-scoped get-or-create + RE owned-project listing + complete"
```

### Task 5.2: Update dialogue ownership to `stakeholder_id` + RE-by-project access

**Files:**
- Modify: `backend/app/routers/dialogue.py`
- Modify: `backend/tests/test_dialogue_router.py` (fix fixtures to new flow)
- Test: existing `backend/tests/test_dialogue_router.py`

- [ ] **Step 1: Update failing fixtures**

Open `backend/tests/test_dialogue_router.py`. Replace any session creation that used `POST /sessions` / `user_id` with the project flow helper:
```python
from app.db.mongo import get_db


async def _member_session(c):
    await c.post("/auth/signup", json={"email": "re@x.com", "password": "Passw0rd!", "real_name": "RE"})
    await get_db().users.update_one({"email": "re@x.com"}, {"$set": {"role": "requirements_engineer"}})
    re_tok = (await c.post("/auth/login", json={"email": "re@x.com", "password": "Passw0rd!"})).json()["access_token"]
    reh = {"Authorization": f"Bearer {re_tok}"}
    pid = (await c.post("/projects", json={"title": "P"}, headers=reh)).json()["id"]
    token = (await c.post(f"/projects/{pid}/invitations", json={"email": "s@x.com"}, headers=reh)).json()["token"]
    s_tok = (await c.post(f"/invitations/{token}/accept", json={"password": "Stake123!", "real_name": "S"})).json()["access_token"]
    sh = {"Authorization": f"Bearer {s_tok}"}
    sid = (await c.post(f"/projects/{pid}/session", headers=sh)).json()["id"]
    return reh, sh, pid, sid
```
Update each dialogue test to use `sh` (stakeholder headers) and `sid` from this helper.

- [ ] **Step 2: Run, confirm failure** — ownership lookups still use `user_id`, so 404s appear.

- [ ] **Step 3: Edit `backend/app/routers/dialogue.py`**

Replace every ownership query `{"_id": oid, "user_id": user_id}` with `{"_id": oid, "stakeholder_id": user_id}` in `post_turn`, `post_message`, and `post_question`.

In `list_turns`, replace the RE-access block:
```python
    session = await db.sessions.find_one({"_id": oid})
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    if session.get("stakeholder_id") != user_id:
        user = await db.users.find_one({"_id": ObjectId(user_id)})
        is_re = user and user.get("role") == "requirements_engineer"
        owns_project = is_re and await db.projects.find_one(
            {"_id": ObjectId(session["project_id"]), "owner_id": user_id}
        )
        if not owns_project:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
```

Also in `_maybe_auto_name`, the field written is `project_title`; change it to `title` to match the new session schema:
```python
        await db.sessions.update_one(
            {"_id": oid},
            {"$set": {"title": title, "auto_named": True, "updated_at": datetime.now(timezone.utc)}},
        )
```
and read `current = session.get("title")`.

- [ ] **Step 4: Run, confirm pass** — `pytest tests/test_dialogue_router.py -v`.

- [ ] **Step 5: Full backend suite** — `pytest -q`. Fix any remaining references to `user_id`/`project_title` on sessions surfaced by failures (e.g. `test_sessions_router.py`, `test_export.py`). Update those tests to the project flow helper.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/dialogue.py backend/tests
git commit -m "refactor(dialogue): project-scoped ownership + RE access via project owner"
```

### Task 5.3: Update export + requirements routers for new ownership

**Files:**
- Modify: `backend/app/routers/export.py`
- Modify: `backend/app/routers/requirements.py`
- Test: `backend/tests/test_export.py` (+ requirements tests if present)

- [ ] **Step 1: Inspect both routers**

Run: `pytest tests/test_export.py -v` and read `backend/app/routers/export.py` + `backend/app/routers/requirements.py` to find every session-ownership check (`user_id` / `project_title`).

- [ ] **Step 2: Apply the same ownership rule**

For any endpoint that loads a session and checks `user_id == caller`, replace with: allow if `session.stakeholder_id == caller` OR caller is an RE who owns `session.project_id` (reuse the pattern from Task 5.2 `list_turns`). Export is RE-only per spec — gate export endpoints behind the RE+owns-project check.

- [ ] **Step 3: Update tests to the project flow helper**, run `pytest -q` → all green.

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/export.py backend/app/routers/requirements.py backend/tests
git commit -m "refactor(export/requirements): project-scoped ownership checks"
```

---

## Phase 6 — Frontend API Clients

### Task 6.1: Projects + invitations API clients

**Files:**
- Create: `frontend/src/api/projects.ts`
- Create: `frontend/src/api/invitations.ts`
- Modify: `frontend/src/api/sessions.ts`

- [ ] **Step 1: Create `frontend/src/api/projects.ts`**

```typescript
import { api } from "./client";

export type Project = {
  id: string;
  title: string;
  background?: string | null;
  goals?: string | null;
  scope?: string | null;
  created_at?: string | null;
};

export type Member = {
  user_id: string;
  email: string;
  real_name: string;
  joined_at?: string | null;
};

export type Invite = {
  id: string;
  email: string;
  status: string;
  token: string;
  accept_url: string;
  expires_at?: string | null;
};

export type ProjectSession = {
  id: string;
  project_id: string;
  stakeholder_id: string;
  title?: string | null;
  status: string;
  phase: string;
  created_at?: string | null;
};

export const listProjects = () => api.get<Project[]>("/projects").then((r) => r.data);
export const getProject = (id: string) => api.get<Project>(`/projects/${id}`).then((r) => r.data);
export const createProject = (body: Partial<Project> & { title: string }) =>
  api.post<Project>("/projects", body).then((r) => r.data);
export const inviteStakeholder = (pid: string, email: string) =>
  api.post<Invite>(`/projects/${pid}/invitations`, { email }).then((r) => r.data);
export const listMembers = (pid: string) =>
  api.get<Member[]>(`/projects/${pid}/members`).then((r) => r.data);
export const listProjectSessions = (pid: string) =>
  api.get<ProjectSession[]>(`/projects/${pid}/sessions`).then((r) => r.data);
export const completeSession = (sid: string) =>
  api.post<ProjectSession>(`/sessions/${sid}/complete`).then((r) => r.data);
```

- [ ] **Step 2: Create `frontend/src/api/invitations.ts`**

```typescript
import { api } from "./client";

export type InvitationView = { email: string; project_title: string; status: string };

export const viewInvitation = (token: string) =>
  api.get<InvitationView>(`/invitations/${token}`).then((r) => r.data);

export const acceptInvitation = (token: string, password: string, real_name?: string) =>
  api
    .post<{ access_token: string }>(`/invitations/${token}/accept`, { password, real_name })
    .then((r) => r.data.access_token);
```

- [ ] **Step 3: Update `frontend/src/api/sessions.ts`**

- Change the `Session` type to match the new `SessionOut`:
```typescript
export type Session = {
  id: string;
  project_id: string;
  stakeholder_id: string;
  title?: string | null;
  status: string;
  phase: string;
  created_at?: string | null;
};
```
- Add the stakeholder get-or-create call and remove the obsolete `createSession(project_title?)`, `archiveSession`, `unarchiveSession`, `deleteSession` exports (the one-session-per-project model no longer uses them):
```typescript
export const openProjectSession = (pid: string) =>
  api.post<Session>(`/projects/${pid}/session`).then((r) => r.data);
```
Keep `getTurns`, `postTurn`, `postMessage`, `postQuestion`, `getRequirements`, `exportSession` as-is.

- [ ] **Step 4: Type-check** — Run: `cd frontend && npx tsc --noEmit`. Fix references to removed exports flagged by the compiler (handled in later tasks).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/projects.ts frontend/src/api/invitations.ts frontend/src/api/sessions.ts
git commit -m "feat(fe-api): projects + invitations clients; project-scoped sessions"
```

---

## Phase 7 — Frontend Invite-Accept Page (public)

### Task 7.1: `InviteAcceptPage`

**Files:**
- Create: `frontend/src/pages/InviteAcceptPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/pages/InviteAcceptPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { viewInvitation, acceptInvitation, type InvitationView } from "../api/invitations";
import { useAuthStore } from "../store/authStore";

export default function InviteAcceptPage() {
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);
  const setRole = useAuthStore((s) => s.setRole);

  const [info, setInfo] = useState<InvitationView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [realName, setRealName] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    viewInvitation(token)
      .then(setInfo)
      .catch((e) => setError(e?.response?.data?.detail ?? "This invitation is invalid or expired."));
  }, [token]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const access = await acceptInvitation(token, password, realName || undefined);
      setToken(access);
      setRole("stakeholder");
      navigate("/", { replace: true });
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Could not accept the invitation.");
      setSubmitting(false);
    }
  }

  if (error && !info)
    return <div className="h-screen flex items-center justify-center text-muted">{error}</div>;
  if (!info)
    return <div className="h-screen flex items-center justify-center text-muted">Loading…</div>;

  return (
    <div className="h-screen flex items-center justify-center bg-background">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 p-6 rounded-xl border border-border">
        <h1 className="text-lg font-semibold">Join “{info.project_title}”</h1>
        <p className="text-sm text-muted">Invitation for {info.email}. Set a password to continue.</p>
        <input
          className="w-full rounded border border-border bg-transparent px-3 py-2"
          placeholder="Your name"
          value={realName}
          onChange={(e) => setRealName(e.target.value)}
        />
        <input
          className="w-full rounded border border-border bg-transparent px-3 py-2"
          type="password"
          placeholder="Password (min 8 chars)"
          value={password}
          minLength={8}
          required
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-sm text-red-500">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded bg-primary text-white py-2 disabled:opacity-50"
        >
          {submitting ? "Joining…" : "Join project"}
        </button>
      </form>
    </div>
  );
}
```

> Tailwind tokens (`bg-background`, `border-border`, `text-muted`, `bg-primary`) follow the existing theme config in `frontend/tailwind.config.js`. If a token name differs, match the names already used in `LoginPage.tsx`.

- [ ] **Step 2: Add public route in `frontend/src/App.tsx`**

Add inside `<Routes>`, OUTSIDE `ProtectedRoute`:
```tsx
import InviteAcceptPage from "./pages/InviteAcceptPage";
// ...
        <Route path="/invite/:token" element={<InviteAcceptPage />} />
```

- [ ] **Step 3: Type-check + manual smoke** — `npx tsc --noEmit`; then with backend running, create an invite as RE, open `/invite/<token>`, set a password, confirm redirect to `/chat`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/InviteAcceptPage.tsx frontend/src/App.tsx
git commit -m "feat(fe): public invite-accept page"
```

---

## Phase 8 — Frontend RE Project Management

### Task 8.1: Projects list + create (`ProjectsPage`)

**Files:**
- Create: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/pages/ProjectsPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects, createProject, type Project } from "../api/projects";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [title, setTitle] = useState("");
  const [background, setBackground] = useState("");

  async function refresh() {
    setProjects(await listProjects());
  }
  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    await createProject({ title: title.trim(), background: background.trim() || undefined });
    setTitle("");
    setBackground("");
    refresh();
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-xl font-semibold">Projects</h1>
      <form onSubmit={onCreate} className="space-y-2 rounded-xl border border-border p-4">
        <input
          className="w-full rounded border border-border bg-transparent px-3 py-2"
          placeholder="Project title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <textarea
          className="w-full rounded border border-border bg-transparent px-3 py-2"
          placeholder="Background / goals / scope (context for the AI)"
          value={background}
          onChange={(e) => setBackground(e.target.value)}
        />
        <button className="rounded bg-primary text-white px-4 py-2">Create project</button>
      </form>
      <ul className="space-y-2">
        {projects.map((p) => (
          <li key={p.id} className="rounded-lg border border-border p-3">
            <Link className="font-medium hover:underline" to={`/projects/${p.id}`}>
              {p.title}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Route it in `App.tsx`** — inside `ProtectedRoute`:
```tsx
import ProjectsPage from "./pages/ProjectsPage";
// ...
          <Route path="/projects" element={<ProjectsPage />} />
```
And change `RoleRedirect` so RE lands on `/projects`:
```tsx
  if (role === "requirements_engineer") return <Navigate to="/projects" replace />;
```

- [ ] **Step 3: Type-check + smoke**, then **commit**

```bash
git add frontend/src/pages/ProjectsPage.tsx frontend/src/App.tsx
git commit -m "feat(fe): RE projects list + create page"
```

### Task 8.2: Project detail — invite + members + sessions (`ProjectDetailPage`)

**Files:**
- Create: `frontend/src/pages/ProjectDetailPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/pages/ProjectDetailPage.tsx`**

```tsx
import { useEffect, useState } from "react";
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

export default function ProjectDetailPage() {
  const { id = "" } = useParams();
  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [sessions, setSessions] = useState<ProjectSession[]>([]);
  const [email, setEmail] = useState("");
  const [lastInvite, setLastInvite] = useState<Invite | null>(null);

  async function refresh() {
    setProject(await getProject(id));
    setMembers(await listMembers(id));
    setSessions(await listProjectSessions(id));
  }
  useEffect(() => {
    refresh();
  }, [id]);

  async function onInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    const inv = await inviteStakeholder(id, email.trim());
    setLastInvite(inv);
    setEmail("");
    refresh();
  }

  async function onComplete(sid: string) {
    await completeSession(sid);
    refresh();
  }

  if (!project) return <div className="p-6 text-muted">Loading…</div>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <Link to="/projects" className="text-sm text-muted hover:underline">← Projects</Link>
      <h1 className="text-xl font-semibold">{project.title}</h1>
      {project.background && <p className="text-sm text-muted whitespace-pre-wrap">{project.background}</p>}

      <section className="rounded-xl border border-border p-4 space-y-2">
        <h2 className="font-medium">Invite a stakeholder</h2>
        <form onSubmit={onInvite} className="flex gap-2">
          <input
            className="flex-1 rounded border border-border bg-transparent px-3 py-2"
            type="email"
            placeholder="stakeholder@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <button className="rounded bg-primary text-white px-4">Invite</button>
        </form>
        {lastInvite && (
          <div className="text-sm">
            <p className="text-muted">Share this link with {lastInvite.email}:</p>
            <code className="block break-all rounded bg-surface px-2 py-1">{lastInvite.accept_url}</code>
          </div>
        )}
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Members ({members.length})</h2>
        <ul className="space-y-1">
          {members.map((m) => (
            <li key={m.user_id} className="text-sm">{m.real_name} — {m.email}</li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="font-medium">Interview sessions</h2>
        <ul className="space-y-2">
          {sessions.map((s) => (
            <li key={s.id} className="flex items-center justify-between rounded-lg border border-border p-3">
              <Link to={`/chat?session=${s.id}`} className="hover:underline">
                {s.title || "Untitled interview"} <span className="text-muted">· {s.status}</span>
              </Link>
              {s.status !== "completed" && (
                <button className="text-sm rounded border border-border px-3 py-1" onClick={() => onComplete(s.id)}>
                  Mark ended
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
```

> `bg-surface` should match an existing token; if absent, reuse a neutral background class already used in `SpecPage.tsx`.

- [ ] **Step 2: Route it in `App.tsx`** — inside `ProtectedRoute`:
```tsx
import ProjectDetailPage from "./pages/ProjectDetailPage";
// ...
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
```

- [ ] **Step 3: Type-check + smoke** (invite shows link; "Mark ended" flips status), then **commit**

```bash
git add frontend/src/pages/ProjectDetailPage.tsx frontend/src/App.tsx
git commit -m "feat(fe): RE project detail — invite, members, sessions, complete"
```

---

## Phase 9 — Stakeholder Project Flow

### Task 9.1: Stakeholder picks project → opens their session; "ended" banner

**Files:**
- Modify: `frontend/src/pages/MainPage.tsx`
- Modify: `frontend/src/store/sessionStore.ts` (if it holds the active session id)
- Test: `frontend/src/store/sessionStore.test.ts` (extend if store changes)

- [ ] **Step 1: Read current `MainPage.tsx` and `sessionStore.ts`**

Understand how the active session is currently selected and how `SessionList` feeds it. The stakeholder no longer freely creates sessions; instead they choose a project (membership) and the app calls `openProjectSession(pid)`.

- [ ] **Step 2: Add a stakeholder project picker**

At the top of the stakeholder flow, fetch the projects the stakeholder belongs to. There is no stakeholder "my projects" endpoint yet — add one in the backend:

In `backend/app/routers/projects.py` add (role-agnostic, returns projects the caller is a member of):
```python
from ..deps import current_user_doc


@router.get("/mine/memberships", response_model=list[ProjectOut])
async def my_member_projects(user: dict = Depends(current_user_doc)):
    db = get_db()
    pids = [m["project_id"] async for m in db.memberships.find({"user_id": user["_id"]})]
    out: list[ProjectOut] = []
    for pid in pids:
        try:
            p = await db.projects.find_one({"_id": ObjectId(pid)})
        except Exception:
            p = None
        if p:
            out.append(_project_out(p))
    return out
```
Add a test in `backend/tests/test_projects_router.py`:
```python
@pytest.mark.asyncio
async def test_stakeholder_lists_member_projects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # build RE + project + invite + accept (reuse helpers from test_sessions_project_scope)
        from tests.test_sessions_project_scope import _re_project_and_invited_stakeholder
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        r = await c.get("/projects/mine/memberships", headers=sh)
        assert [p["id"] for p in r.json()] == [pid]
```
Run `pytest tests/test_projects_router.py -v` → PASS. Add a frontend client in `frontend/src/api/projects.ts`:
```typescript
export const myMemberProjects = () =>
  api.get<Project[]>("/projects/mine/memberships").then((r) => r.data);
```

- [ ] **Step 3: Wire `MainPage.tsx`**

- On load: if `?session=<id>` query param present (RE deep-link), load that session's turns directly.
- Else: call `myMemberProjects()`. If exactly one, auto-open via `openProjectSession(pid)`. If multiple, render a simple project list; selecting one calls `openProjectSession(pid)` and loads turns.
- When the active session `status === "completed"`, render a non-dismissable banner above the chat: **"This requirements elicitation has ended. Thank you!"** and disable the message input (`InputBox`).

Concretely, add near the top of the rendered chat area:
```tsx
{activeSession?.status === "completed" && (
  <div className="rounded-md bg-surface border border-border px-4 py-2 text-sm text-muted">
    This requirements elicitation has ended. Thank you!
  </div>
)}
```
and pass a `disabled={activeSession?.status === "completed"}` prop into `InputBox` (add the prop to `InputBox.tsx`: when `disabled`, render the textarea `disabled` and skip submit).

- [ ] **Step 4: Type-check + smoke**

`npx tsc --noEmit`; then: as a stakeholder with one project, confirm auto-open; as RE click a session deep-link `/chat?session=<id>` and confirm read view; mark the session ended as RE and confirm the stakeholder sees the banner and cannot send.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/projects.py backend/tests/test_projects_router.py frontend/src/api/projects.ts frontend/src/pages/MainPage.tsx frontend/src/components/Dialogue/InputBox.tsx frontend/src/store/sessionStore.ts
git commit -m "feat(fe): stakeholder project picker + ended banner; backend my-memberships"
```

---

## Phase 10 — Cleanup, Docs, Full Verification

### Task 10.1: Remove dead stakeholder-session UI + update docs

**Files:**
- Modify: `frontend/src/components/Sidebar/SessionList.tsx` (remove create/archive/delete actions tied to removed endpoints)
- Modify: `backend/scripts/promote_user.py` (no change needed; verify still valid)
- Modify: `README.md` (document the RE→invite→stakeholder flow + `promote_user.py`)

- [ ] **Step 1: Prune `SessionList.tsx`**

Remove buttons/handlers that called the deleted `createSession` / `archiveSession` / `unarchiveSession` / `deleteSession`. For the stakeholder, the sidebar now lists their project sessions (read/select only). Confirm `npx tsc --noEmit` is clean.

- [ ] **Step 2: Update `README.md`**

Add a short "Roles & onboarding" section:
```markdown
## Roles & onboarding
- Promote a user to Requirements Engineer: `python -m scripts.promote_user <email>` (run in the backend container).
- RE creates a project, sets background/goals, and invites stakeholders by email.
- Email is not sent automatically (FYP scope): the invite link is shown in the RE's project page — copy and share it.
- The stakeholder opens the link, sets a password, and is taken to their interview for that project.
- When elicitation is done, the RE marks the session "ended"; the stakeholder sees an end-of-interview banner.
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Sidebar/SessionList.tsx README.md
git commit -m "chore: prune dead session UI + document multi-stakeholder onboarding"
```

### Task 10.2: Full verification

- [ ] **Step 1: Backend** — `cd backend && pytest -q`. Expected: all green.

- [ ] **Step 2: Frontend unit** — `cd frontend && npm run test`. Expected: all green.

- [ ] **Step 3: Frontend type + build** — `npx tsc --noEmit && npm run build`. Expected: clean.

- [ ] **Step 4: Manual end-to-end** (docker compose up):
  1. Sign up user A; promote to RE via `promote_user.py`.
  2. As A, create a project, invite `b@x.com`, copy the link.
  3. Open the link in a private window; set password as B → lands in B's interview.
  4. B answers a couple of probing questions.
  5. As A, open the project, open B's session (read), then "Mark ended".
  6. As B, reload → see the "elicitation has ended" banner; input disabled.

- [ ] **Step 5: Commit any fixes**, then report completion.

---

## Self-Review Notes (coverage map)

- Spec "双角色 + role 取值" → Task 1.4 (User.role), Phase 2 (role deps).
- Spec "Project / Membership / Invitation 模型" → Tasks 1.1–1.3, indexes 1.5.
- Spec "邀请制(链接显示在 UI、7 天过期、已注册邮箱直接加入)" → Tasks 3.2, 4.1, 4.2, 7.1.
- Spec "Session 改为 project_id + stakeholder_id;一人一项目一会话" → Tasks 1.4, 1.5 (unique index), 5.1.
- Spec "RE 只看自己拥有项目的会话(取代全局)" → Tasks 5.1 (list_project_sessions), 5.2 (list_turns), 5.3 (export).
- Spec "stakeholder 仅看结束状态" → Task 5.1 (`/complete`), 9.1 (banner + disabled input).
- Spec "AI 上下文衔接(project background)" → wired where `ContextManager` summary is built; if not yet consumed, extend `post_turn`/`post_question` to prepend `project.background` to `summary` (do this in Task 5.2 while editing dialogue.py).
- Spec "未来工作:真实邮件" → README note in Task 10.2.
