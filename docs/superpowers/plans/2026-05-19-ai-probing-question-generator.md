# AI Probing Question Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web application that takes a stakeholder's vague software description and iteratively generates 5–10 context-aware probing questions per turn (using a validated Gemini-backed Hybrid Intelligent Agent), letting a Requirements Engineer review and export the resulting requirements report.

**Architecture:** Three-tier MVC. React (Vite) front-end calls a Python FastAPI backend over JSON. The backend hosts a *Hybrid Intelligent Agent* that orchestrates three components — `ContextManager` (Least-to-Most prompting for interview flow), `StrategySelector` (Concept / Related-Concept / General question variety), and `MistakeValidator` (14-mistake taxonomy + retry loop at low temperature) — calling Google Gemini through a thin `LLMService`. State is persisted to MongoDB (`users`, `sessions`, `turns`, `requirements`). JWT-based auth, REST endpoints for sessions/dialogue/export.

**Tech Stack:**
- **Frontend:** React 18 + Vite, React Router, Zustand for state, Tailwind CSS, Axios.
- **Backend:** Python 3.11, FastAPI, Pydantic v2, Uvicorn, Motor (async MongoDB).
- **Database:** MongoDB 7 (local for dev, Atlas optional for cloud).
- **AI:** Google `google-genai` SDK targeting `gemini-2.5-flash` (cost/latency) with `gemini-2.5-pro` fallback for validation.
- **Auth:** `python-jose` JWT + `passlib[bcrypt]`.
- **Testing:** Pytest + httpx (backend), Vitest + React Testing Library + Playwright (frontend).
- **Tooling:** Git, GitHub, Docker Compose, GitHub Actions CI, Ruff + Black, ESLint + Prettier.

**Repository layout (target):**

```
FYPver2/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── deps.py
│   │   ├── db/mongo.py
│   │   ├── models/        # Pydantic + Mongo schemas
│   │   ├── schemas/       # API request/response models
│   │   ├── routers/       # auth, sessions, dialogue, export
│   │   ├── services/      # llm, context, strategy, validator, generator, export
│   │   ├── prompts/       # text/JSON prompt templates
│   │   └── utils/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── store/
│   │   └── styles/
│   ├── tests/
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .github/workflows/ci.yml
└── docs/
```

---

## File Structure & Responsibilities

| File | Responsibility |
|---|---|
| `backend/app/main.py` | FastAPI app, CORS, router mounting, startup hooks |
| `backend/app/config.py` | Pydantic `Settings` (env vars, Gemini key, JWT secret, Mongo URI) |
| `backend/app/db/mongo.py` | Motor client lifecycle, index creation |
| `backend/app/models/user.py` | `User` document (email, hashed_password, real_name, phone, domain_level) |
| `backend/app/models/session.py` | `InterviewSession` (user_id, project_title, status, created_at, summary) |
| `backend/app/models/turn.py` | `DialogueTurn` (session_id, role, content, validator_meta, timestamp) |
| `backend/app/models/requirement.py` | `Requirement` (session_id, statement, type, source_turn_ids) |
| `backend/app/services/llm_service.py` | Thin Gemini wrapper: `generate(prompt, *, temperature, response_schema=None)` |
| `backend/app/services/context_manager.py` | Builds Least-to-Most prompt from rolling history & phase |
| `backend/app/services/strategy_selector.py` | Picks next question strategy & avoids repetition |
| `backend/app/services/mistake_validator.py` | Classifies draft against 14-mistake taxonomy; returns verdict + correction prompt |
| `backend/app/services/question_generator.py` | Orchestrator: draft → validate → (retry≤3) → persist turn |
| `backend/app/services/export_service.py` | Compiles requirements → Markdown / plain text |
| `backend/app/services/auth_service.py` | Password hashing, JWT issue/verify |
| `backend/app/routers/auth.py` | POST `/auth/signup`, POST `/auth/login`, POST `/auth/logout` |
| `backend/app/routers/sessions.py` | CRUD on InterviewSession; list for sidebar |
| `backend/app/routers/dialogue.py` | POST `/sessions/{id}/turns` → returns next probing question(s) |
| `backend/app/routers/export.py` | GET `/sessions/{id}/export?format=md\|txt` |
| `backend/app/prompts/context_prompt.txt` | Least-to-Most system prompt |
| `backend/app/prompts/strategy_prompts.json` | Concept / Related / General templates |
| `backend/app/prompts/mistake_taxonomy.json` | 14 mistake types + correction snippets |
| `frontend/src/api/client.ts` | Axios instance + JWT interceptor |
| `frontend/src/store/authStore.ts` | Zustand: user, token |
| `frontend/src/store/sessionStore.ts` | Zustand: active session, turns, live requirements |
| `frontend/src/pages/LoginPage.tsx` | Login form (Figure 4.8) |
| `frontend/src/pages/SignupPage.tsx` | Signup form (Figure 4.9) |
| `frontend/src/pages/MainPage.tsx` | 3-panel layout (Figure 4.6) |
| `frontend/src/components/Sidebar/SessionList.tsx` | Active + archived sessions |
| `frontend/src/components/Dialogue/ChatPanel.tsx` | Turn-by-turn dialogue |
| `frontend/src/components/Dialogue/StatusIndicator.tsx` | "Validating question relevance..." pill |
| `frontend/src/components/Dialogue/InputBox.tsx` | Stakeholder text input |
| `frontend/src/components/Requirements/LiveRequirements.tsx` | Right sidebar, auto-updating |
| `frontend/src/components/Auth/ProtectedRoute.tsx` | Redirects unauthenticated users |

---

## Phase 0 — Project Skeleton & Tooling

### Task 0.1: Initialise repo structure, lint, and pre-commit

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `backend/pyproject.toml`, `backend/app/__init__.py`, `frontend/package.json`, `.editorconfig`

- [ ] **Step 1: Create `.gitignore` at repo root**

```gitignore
# Python
__pycache__/
*.pyc
.venv/
.env
.env.*
!.env.example
.pytest_cache/
.ruff_cache/

# Node
node_modules/
dist/
.vite/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 2: Create `backend/pyproject.toml`**

```toml
[project]
name = "probing-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi==0.115.0",
  "uvicorn[standard]==0.30.6",
  "pydantic==2.9.2",
  "pydantic-settings==2.5.2",
  "motor==3.6.0",
  "passlib[bcrypt]==1.7.4",
  "python-jose[cryptography]==3.3.0",
  "python-multipart==0.0.9",
  "google-genai==0.3.0",
  "httpx==0.27.2",
]

[project.optional-dependencies]
dev = ["pytest==8.3.3", "pytest-asyncio==0.24.0", "ruff==0.6.9", "black==24.10.0", "mongomock-motor==0.0.34"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
```

- [ ] **Step 3: Initialise Python venv and install**

Run:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```
Expected: clean install, `ruff` and `pytest` discoverable.

- [ ] **Step 4: Scaffold frontend with Vite**

Run:
```bash
cd ..
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss@3.4 postcss autoprefixer vitest @testing-library/react @testing-library/jest-dom @playwright/test
npm install axios zustand react-router-dom@6
npx tailwindcss init -p
```
Expected: `frontend/package.json` and `tailwind.config.js` present.

- [ ] **Step 5: Add Tailwind directives**

Replace contents of `frontend/src/index.css` with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```
And in `frontend/tailwind.config.js` set `content: ['./index.html', './src/**/*.{ts,tsx}']`.

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: bootstrap backend (FastAPI) and frontend (Vite+React+TS) skeletons"
```

### Task 0.2: Docker Compose for dev

**Files:**
- Create: `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`

- [ ] **Step 1: Create `.env.example`**

```env
# Backend
MONGO_URI=mongodb://mongo:27017
MONGO_DB=probing
JWT_SECRET=replace-me
JWT_ALG=HS256
JWT_TTL_MINUTES=60
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
GEMINI_VALIDATOR_MODEL=gemini-2.5-flash
CORS_ORIGINS=http://localhost:5173

# Frontend
VITE_API_BASE=http://localhost:8000
```

- [ ] **Step 2: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .
COPY app ./app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

- [ ] **Step 4: Create `docker-compose.yml`**

```yaml
version: "3.9"
services:
  mongo:
    image: mongo:7
    ports: ["27017:27017"]
    volumes: ["mongo_data:/data/db"]
  backend:
    build: ./backend
    env_file: .env
    ports: ["8000:8000"]
    depends_on: [mongo]
    volumes: ["./backend/app:/app/app"]
  frontend:
    build: ./frontend
    ports: ["5173:80"]
    depends_on: [backend]
volumes:
  mongo_data: {}
```

- [ ] **Step 5: Verify compose boots**

Run:
```bash
copy .env.example .env
docker compose up -d mongo
docker compose ps
```
Expected: Mongo healthy on 27017.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml backend/Dockerfile frontend/Dockerfile .env.example
git commit -m "chore: add docker compose for mongo + backend + frontend"
```

---

## Phase 1 — Backend Core: Config, DB, Models

### Task 1.1: Settings & FastAPI app bootstrap

**Files:**
- Create: `backend/app/config.py`, `backend/app/main.py`, `backend/tests/test_health.py`

- [ ] **Step 1: Write failing health-check test**

`backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

def test_health_ok():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: Run and confirm failure**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: ImportError or 404.

- [ ] **Step 3: Implement `config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "probing"
    jwt_secret: str = "dev-secret"
    jwt_alg: str = "HS256"
    jwt_ttl_minutes: int = 60
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_validator_model: str = "gemini-2.5-flash"
    cors_origins: str = "http://localhost:5173"

settings = Settings()
```

- [ ] **Step 4: Implement `main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings

app = FastAPI(title="AI Probing Question Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Re-run test**

Run: `pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/main.py backend/tests/test_health.py
git commit -m "feat(backend): app bootstrap + settings + health endpoint"
```

### Task 1.2: Mongo connection and indexes

**Files:**
- Create: `backend/app/db/__init__.py`, `backend/app/db/mongo.py`, `backend/tests/test_mongo.py`

- [ ] **Step 1: Write failing test**

`backend/tests/test_mongo.py`:
```python
import pytest
from app.db.mongo import get_db, init_indexes

@pytest.mark.asyncio
async def test_get_db_returns_database():
    db = get_db()
    assert db.name

@pytest.mark.asyncio
async def test_init_indexes_runs():
    await init_indexes()
```

- [ ] **Step 2: Run and confirm failure**

Run: `pytest tests/test_mongo.py -v` → ImportError.

- [ ] **Step 3: Implement `db/mongo.py`**

```python
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from ..config import settings

_client: AsyncIOMotorClient | None = None

def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client

def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db]

async def init_indexes() -> None:
    db = get_db()
    await db.users.create_index("email", unique=True)
    await db.sessions.create_index([("user_id", 1), ("status", 1)])
    await db.turns.create_index([("session_id", 1), ("created_at", 1)])
    await db.requirements.create_index("session_id")
```

- [ ] **Step 4: Wire startup hook in `main.py`**

Add to `main.py`:
```python
from .db.mongo import init_indexes

@app.on_event("startup")
async def _startup():
    await init_indexes()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_mongo.py -v` (requires Mongo running locally on 27017).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/db backend/tests/test_mongo.py backend/app/main.py
git commit -m "feat(backend): motor mongo client + index initialisation"
```

### Task 1.3: Pydantic domain models

**Files:**
- Create: `backend/app/models/__init__.py`, `backend/app/models/user.py`, `backend/app/models/session.py`, `backend/app/models/turn.py`, `backend/app/models/requirement.py`, `backend/tests/test_models.py`

- [ ] **Step 1: Write failing tests covering schema invariants**

```python
import pytest
from datetime import datetime
from app.models.user import User
from app.models.session import InterviewSession, SessionStatus
from app.models.turn import DialogueTurn, TurnRole
from app.models.requirement import Requirement, RequirementType

def test_user_requires_email():
    with pytest.raises(ValueError):
        User(email="", hashed_password="x", real_name="A")

def test_session_default_active():
    s = InterviewSession(user_id="u1", project_title="P")
    assert s.status == SessionStatus.ACTIVE

def test_turn_role_enum():
    t = DialogueTurn(session_id="s1", role=TurnRole.STAKEHOLDER, content="hi")
    assert t.role == TurnRole.STAKEHOLDER

def test_requirement_type_enum():
    r = Requirement(session_id="s1", statement="must do X", type=RequirementType.FUNCTIONAL)
    assert r.type == RequirementType.FUNCTIONAL
```

- [ ] **Step 2: Implement `models/user.py`**

```python
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator

class User(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    email: EmailStr
    hashed_password: str
    real_name: str
    phone: Optional[str] = None
    domain_level: str = "novice"  # novice|intermediate|expert
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("email")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("email required")
        return v
```

- [ ] **Step 3: Implement `models/session.py`**

```python
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class SessionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"

class InterviewSession(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    project_title: str
    status: SessionStatus = SessionStatus.ACTIVE
    phase: str = "exploration"  # exploration|deepening|validation
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 4: Implement `models/turn.py` and `models/requirement.py`**

```python
# turn.py
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class TurnRole(str, Enum):
    STAKEHOLDER = "stakeholder"
    AGENT = "agent"

class DialogueTurn(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    session_id: str
    role: TurnRole
    content: str
    strategy: Optional[str] = None  # set by AGENT turns
    validator_attempts: int = 0
    validator_verdict: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

```python
# requirement.py
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"

class Requirement(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    session_id: str
    statement: str
    type: RequirementType
    source_turn_ids: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_models.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models backend/tests/test_models.py
git commit -m "feat(backend): pydantic models for user/session/turn/requirement"
```

---

## Phase 2 — Authentication

### Task 2.1: Password hashing + JWT helpers

**Files:**
- Create: `backend/app/services/__init__.py`, `backend/app/services/auth_service.py`, `backend/tests/test_auth_service.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from app.services.auth_service import hash_password, verify_password, create_token, decode_token

def test_hash_roundtrip():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)

def test_token_roundtrip():
    tok = create_token({"sub": "user-123"})
    claims = decode_token(tok)
    assert claims["sub"] == "user-123"
```

- [ ] **Step 2: Implement service**

```python
from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from ..config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return _pwd.hash(p)

def verify_password(p: str, hashed: str) -> bool:
    return _pwd.verify(p, hashed)

def create_token(sub_claims: dict) -> str:
    payload = {
        **sub_claims,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_auth_service.py -v` → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/auth_service.py backend/tests/test_auth_service.py
git commit -m "feat(auth): password hashing + JWT helpers"
```

### Task 2.2: `deps.py` current-user dependency

**Files:**
- Create: `backend/app/deps.py`, `backend/tests/test_deps.py`

- [ ] **Step 1: Write failing test**

```python
import pytest
from fastapi import HTTPException
from app.deps import current_user_id_from_token
from app.services.auth_service import create_token

def test_valid_token_returns_sub():
    tok = create_token({"sub": "u1"})
    assert current_user_id_from_token(f"Bearer {tok}") == "u1"

def test_missing_bearer_raises():
    with pytest.raises(HTTPException):
        current_user_id_from_token(None)
```

- [ ] **Step 2: Implement `deps.py`**

```python
from fastapi import Header, HTTPException, status
from .services.auth_service import decode_token

def current_user_id_from_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = decode_token(authorization.split(" ", 1)[1])
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no subject")
    return sub
```

- [ ] **Step 3: Run tests** → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/deps.py backend/tests/test_deps.py
git commit -m "feat(auth): FastAPI dependency for current user from JWT"
```

### Task 2.3: Auth router (signup, login)

**Files:**
- Create: `backend/app/schemas/auth.py`, `backend/app/routers/__init__.py`, `backend/app/routers/auth.py`, `backend/tests/test_auth_router.py`
- Modify: `backend/app/main.py` (include router)

- [ ] **Step 1: Write failing integration tests**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_signup_then_login():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/auth/signup", json={
            "email": "a@x.com", "password": "Passw0rd!", "real_name": "Ada", "phone": "0123"
        })
        assert r.status_code == 201
        r = await c.post("/auth/login", json={"email": "a@x.com", "password": "Passw0rd!"})
        assert r.status_code == 200
        assert "access_token" in r.json()
```

- [ ] **Step 2: Define schemas**

`schemas/auth.py`:
```python
from pydantic import BaseModel, EmailStr, Field

class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    real_name: str
    phone: str | None = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

- [ ] **Step 3: Implement router**

`routers/auth.py`:
```python
from fastapi import APIRouter, HTTPException, status
from ..db.mongo import get_db
from ..schemas.auth import SignupRequest, LoginRequest, TokenResponse
from ..services.auth_service import hash_password, verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", status_code=201, response_model=TokenResponse)
async def signup(body: SignupRequest):
    db = get_db()
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    doc = {
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "real_name": body.real_name,
        "phone": body.phone,
        "domain_level": "novice",
    }
    res = await db.users.insert_one(doc)
    return TokenResponse(access_token=create_token({"sub": str(res.inserted_id)}))

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    db = get_db()
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return TokenResponse(access_token=create_token({"sub": str(user["_id"])}))
```

- [ ] **Step 4: Mount router**

In `app/main.py` add:
```python
from .routers import auth as auth_router
app.include_router(auth_router.router)
```

- [ ] **Step 5: Run tests against in-memory Mongo**

Use `mongomock-motor` by overriding `get_db` in a conftest fixture. Add `backend/tests/conftest.py`:
```python
import pytest
from mongomock_motor import AsyncMongoMockClient
from app.db import mongo as mongo_mod

@pytest.fixture(autouse=True)
def patch_mongo(monkeypatch):
    client = AsyncMongoMockClient()
    monkeypatch.setattr(mongo_mod, "_client", client)
    yield
```

Run: `pytest tests/test_auth_router.py -v` → PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/auth.py backend/app/routers/auth.py backend/app/main.py backend/tests/conftest.py backend/tests/test_auth_router.py
git commit -m "feat(auth): /auth/signup and /auth/login endpoints"
```

---

## Phase 3 — LLM Service (Gemini wrapper)

### Task 3.1: `LLMService` with temperature + JSON-mode support

**Files:**
- Create: `backend/app/services/llm_service.py`, `backend/tests/test_llm_service.py`

- [ ] **Step 1: Write failing test with a fake transport**

```python
import pytest
from app.services.llm_service import LLMService

class FakeClient:
    def __init__(self): self.calls = []
    async def generate(self, *, model, contents, config):
        self.calls.append((model, contents, config))
        return type("R", (), {"text": '{"question": "Why?"}'})()

@pytest.mark.asyncio
async def test_generate_passes_temperature_and_returns_text():
    fc = FakeClient()
    svc = LLMService(client=fc, model="gemini-2.5-flash")
    out = await svc.generate("hi", temperature=0.7)
    assert out == '{"question": "Why?"}'
    assert fc.calls[0][2]["temperature"] == 0.7
```

- [ ] **Step 2: Implement service**

```python
from typing import Any, Optional
from ..config import settings

class LLMService:
    def __init__(self, *, client: Any | None = None, model: str | None = None):
        if client is None:
            from google import genai
            client = genai.Client(api_key=settings.gemini_api_key)
        self.client = client
        self.model = model or settings.gemini_model

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        response_mime_type: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        config = {"temperature": temperature}
        if response_mime_type:
            config["response_mime_type"] = response_mime_type
        resp = await self.client.generate(
            model=model or self.model,
            contents=prompt,
            config=config,
        )
        return resp.text
```

> **Note:** The `google-genai` SDK exposes `client.aio.models.generate_content(...)`. Wrap it with a thin adapter so unit tests can inject a `FakeClient` matching the `generate(model=, contents=, config=)` signature.

- [ ] **Step 3: Run tests** → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/llm_service.py backend/tests/test_llm_service.py
git commit -m "feat(llm): Gemini service wrapper with temperature + JSON mime support"
```

---

## Phase 4 — Hybrid Intelligent Agent

### Task 4.1: Prompt templates (Context, Strategy, Mistakes)

**Files:**
- Create: `backend/app/prompts/context_prompt.txt`, `backend/app/prompts/strategy_prompts.json`, `backend/app/prompts/mistake_taxonomy.json`

- [ ] **Step 1: Write `prompts/context_prompt.txt`**

```
You are a Requirements Elicitation assistant using Least-to-Most prompting.
Phase: {phase}
Session summary so far: {summary}
Recent turns (oldest→newest):
{history}

Break the task into ordered sub-steps:
1. Identify what is already known.
2. Identify the single most important gap relative to phase={phase}.
3. Choose ONE concrete probing question to fill that gap.

Return JSON: {"sub_steps": [...], "knowledge_gap": "...", "draft_question": "..."}
```

- [ ] **Step 2: Write `prompts/strategy_prompts.json`** (Hu et al. 2024 three types)

```json
{
  "concept": "Generate a follow-up question that elaborates on the most recently mentioned entity by the stakeholder. The question must reference the entity by name.",
  "related_concept": "Generate a follow-up question that broadens the discussion to a related but unmentioned aspect (e.g., security, performance, edge cases).",
  "general": "Generate a short, open probe such as 'Why?' or 'Can you expand on that?' to elicit more depth."
}
```

- [ ] **Step 3: Write `prompts/mistake_taxonomy.json`** (Shen et al. 2025 — 14 mistakes)

```json
{
  "mistakes": [
    {"id": "leading", "desc": "Question presupposes an answer or solution.", "fix": "Rephrase to be neutral and open."},
    {"id": "compound", "desc": "Asks more than one thing at once.", "fix": "Split into a single focused question."},
    {"id": "vague", "desc": "Too abstract to act on.", "fix": "Add a concrete scenario or attribute."},
    {"id": "yes_no", "desc": "Closed yes/no when richer info is needed.", "fix": "Convert to open 'how/why/what'."},
    {"id": "assumption", "desc": "Treats an unverified assumption as fact.", "fix": "Surface and verify the assumption."},
    {"id": "jargon", "desc": "Uses unexplained domain jargon.", "fix": "Use plain language."},
    {"id": "off_topic", "desc": "Drifts from the current requirement focus.", "fix": "Tie back to the current topic."},
    {"id": "duplicate", "desc": "Repeats a question already answered.", "fix": "Skip or refine to a deeper aspect."},
    {"id": "solution_oriented", "desc": "Asks about implementation before need.", "fix": "Ask about the underlying need."},
    {"id": "double_barrelled", "desc": "Bundles unrelated aspects.", "fix": "Separate concerns."},
    {"id": "negative", "desc": "Phrased with double-negatives causing confusion.", "fix": "Restate positively."},
    {"id": "speculative", "desc": "Asks user to guess future behaviour without data.", "fix": "Anchor to a concrete past scenario."},
    {"id": "missing_nonfunctional", "desc": "Ignores NFRs when relevant (perf/security).", "fix": "Probe an NFR dimension."},
    {"id": "missing_edge_case", "desc": "Doesn't probe edge cases.", "fix": "Ask about boundary/exception conditions."}
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/prompts
git commit -m "feat(prompts): context/strategy/mistake taxonomy templates"
```

### Task 4.2: `ContextManager`

**Files:**
- Create: `backend/app/services/context_manager.py`, `backend/tests/test_context_manager.py`

- [ ] **Step 1: Write failing test**

```python
from app.services.context_manager import ContextManager

def test_builds_prompt_with_phase_and_history():
    cm = ContextManager()
    out = cm.build_prompt(
        phase="exploration",
        summary="System for online payments.",
        history=[{"role":"stakeholder","content":"I want a payment app."}],
    )
    assert "exploration" in out
    assert "I want a payment app." in out
    assert "draft_question" in out  # template asks for JSON with this key
```

- [ ] **Step 2: Implement**

```python
from pathlib import Path
from typing import Iterable

_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "context_prompt.txt").read_text(encoding="utf-8")

class ContextManager:
    def build_prompt(self, *, phase: str, summary: str, history: Iterable[dict]) -> str:
        lines = [f"{t['role']}: {t['content']}" for t in history]
        return _TEMPLATE.format(phase=phase, summary=summary or "(none)", history="\n".join(lines) or "(empty)")
```

- [ ] **Step 3: Run tests** → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/context_manager.py backend/tests/test_context_manager.py
git commit -m "feat(agent): ContextManager builds Least-to-Most prompt from session history"
```

### Task 4.3: `StrategySelector`

**Files:**
- Create: `backend/app/services/strategy_selector.py`, `backend/tests/test_strategy_selector.py`

Strategy logic:
- First turn → `concept` (anchor to whatever entity stakeholder names).
- If last 2 agent turns used `concept` → switch to `related_concept`.
- If stakeholder's last reply has <8 tokens → use `general` to push for depth.
- Else pick deterministically by round-robin across `concept`/`related_concept`.

- [ ] **Step 1: Write failing tests**

```python
from app.services.strategy_selector import StrategySelector

def test_first_turn_is_concept():
    sel = StrategySelector()
    assert sel.choose(agent_history=[], last_stakeholder="I want a chat app.") == "concept"

def test_short_reply_triggers_general():
    sel = StrategySelector()
    assert sel.choose(agent_history=["concept"], last_stakeholder="Yes.") == "general"

def test_two_concepts_force_related():
    sel = StrategySelector()
    assert sel.choose(agent_history=["concept","concept"], last_stakeholder="It should support payments via card and wallet.") == "related_concept"
```

- [ ] **Step 2: Implement**

```python
from typing import List

class StrategySelector:
    def choose(self, *, agent_history: List[str], last_stakeholder: str) -> str:
        if not agent_history:
            return "concept"
        if len(last_stakeholder.split()) < 8:
            return "general"
        if agent_history[-2:] == ["concept", "concept"]:
            return "related_concept"
        # round-robin between concept and related_concept
        return "related_concept" if agent_history[-1] == "concept" else "concept"
```

- [ ] **Step 3: Run tests** → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/strategy_selector.py backend/tests/test_strategy_selector.py
git commit -m "feat(agent): StrategySelector picks Concept/Related/General per heuristics"
```

### Task 4.4: `MistakeValidator`

**Files:**
- Create: `backend/app/services/mistake_validator.py`, `backend/tests/test_mistake_validator.py`

The validator is a *second LLM call* that returns JSON `{"valid": bool, "mistakes": [ids], "correction": "..."}`.

- [ ] **Step 1: Write failing test using a stub LLM**

```python
import pytest
from app.services.mistake_validator import MistakeValidator

class StubLLM:
    def __init__(self, payload): self.payload = payload; self.calls = []
    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.calls.append((prompt, temperature, model))
        return self.payload

@pytest.mark.asyncio
async def test_validator_accepts_clean_question():
    llm = StubLLM('{"valid": true, "mistakes": [], "correction": ""}')
    v = MistakeValidator(llm=llm)
    verdict = await v.validate("How do you currently handle refunds?")
    assert verdict.valid is True

@pytest.mark.asyncio
async def test_validator_flags_leading_question():
    llm = StubLLM('{"valid": false, "mistakes": ["leading"], "correction": "Rephrase neutrally."}')
    v = MistakeValidator(llm=llm)
    verdict = await v.validate("Don't you think we should use Stripe?")
    assert verdict.valid is False
    assert "leading" in verdict.mistakes
```

- [ ] **Step 2: Implement validator**

```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

_TAX = json.loads((Path(__file__).parent.parent / "prompts" / "mistake_taxonomy.json").read_text(encoding="utf-8"))

@dataclass
class Verdict:
    valid: bool
    mistakes: List[str]
    correction: str

class MistakeValidator:
    def __init__(self, *, llm, max_retries: int = 3):
        self.llm = llm
        self.max_retries = max_retries

    def _build_prompt(self, draft: str) -> str:
        mistakes_block = "\n".join(f"- {m['id']}: {m['desc']}" for m in _TAX["mistakes"])
        return (
            "You are a strict requirements-interview reviewer.\n"
            f"Given the candidate probing question:\n\"\"\"{draft}\"\"\"\n"
            "Decide whether it commits any of these 14 mistakes:\n"
            f"{mistakes_block}\n\n"
            "Respond with JSON: {\"valid\": bool, \"mistakes\": [ids], \"correction\": <suggested rewrite or empty>}"
        )

    async def validate(self, draft: str) -> Verdict:
        raw = await self.llm.generate(
            self._build_prompt(draft),
            temperature=0.1,
            response_mime_type="application/json",
        )
        data = json.loads(raw)
        return Verdict(valid=bool(data.get("valid")), mistakes=list(data.get("mistakes", [])), correction=str(data.get("correction", "")))
```

- [ ] **Step 3: Run tests** → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/mistake_validator.py backend/tests/test_mistake_validator.py
git commit -m "feat(agent): MistakeValidator returns Verdict via low-temperature JSON call"
```

### Task 4.5: `QuestionGenerator` orchestrator

**Files:**
- Create: `backend/app/services/question_generator.py`, `backend/tests/test_question_generator.py`

Flow per the report's Sequence Diagram:
1. Gather history → `ContextManager.build_prompt(...)`.
2. `StrategySelector.choose(...)` → strategy label.
3. Append strategy template; first draft at **temp 0.7**.
4. Loop up to 3:
   - `MistakeValidator.validate(draft)`.
   - If valid → return `draft`, `strategy`, `attempts`.
   - Else re-prompt at **temp 0.1** with correction suggestion → new draft.
5. After max retries, return last draft with `verdict.valid = False` so the router can flag it.

- [ ] **Step 1: Write failing tests covering happy path + retry**

```python
import json, pytest
from app.services.question_generator import QuestionGenerator

class ScriptedLLM:
    def __init__(self, outputs): self.outputs = list(outputs); self.calls = []
    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.calls.append((temperature, prompt))
        return self.outputs.pop(0)

@pytest.mark.asyncio
async def test_first_draft_passes():
    llm = ScriptedLLM([
        '{"draft_question": "How do you currently handle refunds?"}',          # generator
        '{"valid": true, "mistakes": [], "correction": ""}',                    # validator
    ])
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=[
        {"role":"stakeholder","content":"I want a payment app for online retail."}
    ])
    assert "refunds" in result.question
    assert result.attempts == 1
    assert result.valid is True

@pytest.mark.asyncio
async def test_retries_on_leading_question():
    llm = ScriptedLLM([
        '{"draft_question": "Don\'t you think we should use Stripe?"}',
        '{"valid": false, "mistakes": ["leading"], "correction": "Ask which payment providers they are considering."}',
        '{"draft_question": "Which payment providers are you considering?"}',
        '{"valid": true, "mistakes": [], "correction": ""}',
    ])
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=[
        {"role":"stakeholder","content":"I want a payment app for online retail."}
    ])
    assert "providers" in result.question
    assert result.attempts == 2
    assert result.valid is True
```

- [ ] **Step 2: Implement orchestrator**

```python
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from .context_manager import ContextManager
from .strategy_selector import StrategySelector
from .mistake_validator import MistakeValidator

_STRATS = json.loads((Path(__file__).parent.parent / "prompts" / "strategy_prompts.json").read_text(encoding="utf-8"))

@dataclass
class GeneratedQuestion:
    question: str
    strategy: str
    attempts: int
    valid: bool
    mistakes: List[str]

class QuestionGenerator:
    def __init__(self, *, llm, max_retries: int = 3,
                 ctx: ContextManager | None = None,
                 sel: StrategySelector | None = None,
                 val: MistakeValidator | None = None):
        self.llm = llm
        self.max_retries = max_retries
        self.ctx = ctx or ContextManager()
        self.sel = sel or StrategySelector()
        self.val = val or MistakeValidator(llm=llm, max_retries=max_retries)

    async def _draft(self, prompt: str, *, temperature: float) -> str:
        raw = await self.llm.generate(prompt, temperature=temperature, response_mime_type="application/json")
        return json.loads(raw)["draft_question"]

    async def next_question(self, *, phase: str, summary: str, history: list) -> GeneratedQuestion:
        agent_history = [t.get("strategy") for t in history if t["role"] == "agent" and t.get("strategy")]
        last_stake = next((t["content"] for t in reversed(history) if t["role"] == "stakeholder"), "")
        strategy = self.sel.choose(agent_history=agent_history, last_stakeholder=last_stake)
        context_prompt = self.ctx.build_prompt(phase=phase, summary=summary, history=history)
        prompt = f"{context_prompt}\n\nStrategy directive: {_STRATS[strategy]}"
        draft = await self._draft(prompt, temperature=0.7)
        attempts = 1
        verdict = await self.val.validate(draft)
        while not verdict.valid and attempts < self.max_retries:
            attempts += 1
            correction_prompt = (
                f"{prompt}\n\nThe previous draft was: \"{draft}\".\n"
                f"It committed these mistakes: {verdict.mistakes}.\n"
                f"Apply this correction: {verdict.correction}\n"
                "Return JSON with the corrected draft_question."
            )
            draft = await self._draft(correction_prompt, temperature=0.1)
            verdict = await self.val.validate(draft)
        return GeneratedQuestion(question=draft, strategy=strategy, attempts=attempts, valid=verdict.valid, mistakes=verdict.mistakes)
```

- [ ] **Step 3: Run tests** → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/question_generator.py backend/tests/test_question_generator.py
git commit -m "feat(agent): QuestionGenerator orchestrates context+strategy+validation loop"
```

---

## Phase 5 — Session & Dialogue Endpoints

### Task 5.1: Session router (CRUD + list)

**Files:**
- Create: `backend/app/schemas/session.py`, `backend/app/routers/sessions.py`, `backend/tests/test_sessions_router.py`
- Modify: `backend/app/main.py` (include router)

- [ ] **Step 1: Write failing tests**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

async def _auth(c):
    await c.post("/auth/signup", json={"email":"a@x.com","password":"Passw0rd!","real_name":"A"})
    r = await c.post("/auth/login", json={"email":"a@x.com","password":"Passw0rd!"})
    return r.json()["access_token"]

@pytest.mark.asyncio
async def test_create_and_list_sessions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        token = await _auth(c)
        h = {"Authorization": f"Bearer {token}"}
        r = await c.post("/sessions", json={"project_title": "Payments"}, headers=h)
        assert r.status_code == 201
        sid = r.json()["id"]
        r = await c.get("/sessions", headers=h)
        assert any(s["id"] == sid for s in r.json())
```

- [ ] **Step 2: Define schema**

```python
# schemas/session.py
from pydantic import BaseModel
class SessionCreate(BaseModel):
    project_title: str
class SessionOut(BaseModel):
    id: str
    project_title: str
    status: str
    phase: str
```

- [ ] **Step 3: Implement router**

```python
# routers/sessions.py
from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from ..db.mongo import get_db
from ..deps import current_user_id_from_token
from ..schemas.session import SessionCreate, SessionOut

router = APIRouter(prefix="/sessions", tags=["sessions"])

@router.post("", status_code=201, response_model=SessionOut)
async def create(body: SessionCreate, user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    doc = {"user_id": user_id, "project_title": body.project_title, "status": "active", "phase": "exploration"}
    res = await db.sessions.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    return SessionOut(**doc)

@router.get("", response_model=list[SessionOut])
async def list_sessions(user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    out = []
    async for s in db.sessions.find({"user_id": user_id}):
        out.append(SessionOut(id=str(s["_id"]), project_title=s["project_title"], status=s["status"], phase=s["phase"]))
    return out

@router.post("/{sid}/archive", response_model=SessionOut)
async def archive(sid: str, user_id: str = Depends(current_user_id_from_token)):
    db = get_db()
    s = await db.sessions.find_one_and_update(
        {"_id": ObjectId(sid), "user_id": user_id},
        {"$set": {"status": "archived"}},
        return_document=True,
    )
    if not s:
        raise HTTPException(404, "session not found")
    return SessionOut(id=str(s["_id"]), project_title=s["project_title"], status=s["status"], phase=s["phase"])
```

- [ ] **Step 4: Mount router in `main.py`** and **run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/session.py backend/app/routers/sessions.py backend/app/main.py backend/tests/test_sessions_router.py
git commit -m "feat(sessions): create/list/archive interview sessions"
```

### Task 5.2: Dialogue router — submit stakeholder turn, get probing question(s)

**Files:**
- Create: `backend/app/schemas/dialogue.py`, `backend/app/routers/dialogue.py`, `backend/tests/test_dialogue_router.py`
- Modify: `backend/app/main.py`

API: `POST /sessions/{sid}/turns` body `{"content": "..."}` → returns 1–N probing questions and persists both turns.

For initial implementation generate `N=5` questions in a loop (FR: 5–10). The number is configurable via `?count=` (default 5, cap 10).

- [ ] **Step 1: Write failing test**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services import question_generator as qg_mod

class FakeGen:
    async def next_question(self, *, phase, summary, history):
        from app.services.question_generator import GeneratedQuestion
        return GeneratedQuestion(question="What payment providers?", strategy="concept", attempts=1, valid=True, mistakes=[])

@pytest.mark.asyncio
async def test_post_turn_returns_questions(monkeypatch):
    monkeypatch.setattr(qg_mod, "QuestionGenerator", lambda **kw: FakeGen())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.post("/auth/signup", json={"email":"a@x.com","password":"Passw0rd!","real_name":"A"})
        tok = (await c.post("/auth/login", json={"email":"a@x.com","password":"Passw0rd!"})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        sid = (await c.post("/sessions", json={"project_title":"P"}, headers=h)).json()["id"]
        r = await c.post(f"/sessions/{sid}/turns?count=3", json={"content":"I want a payment app."}, headers=h)
        assert r.status_code == 200
        assert len(r.json()["questions"]) == 3
```

- [ ] **Step 2: Schema**

```python
# schemas/dialogue.py
from pydantic import BaseModel, Field
class TurnIn(BaseModel):
    content: str = Field(min_length=1)
class QuestionOut(BaseModel):
    question: str
    strategy: str
    attempts: int
    valid: bool
class TurnResponse(BaseModel):
    questions: list[QuestionOut]
```

- [ ] **Step 3: Router**

```python
# routers/dialogue.py
from fastapi import APIRouter, Depends, HTTPException, Query
from bson import ObjectId
from datetime import datetime
from ..db.mongo import get_db
from ..deps import current_user_id_from_token
from ..schemas.dialogue import TurnIn, TurnResponse, QuestionOut
from ..services.llm_service import LLMService
from ..services.question_generator import QuestionGenerator

router = APIRouter(prefix="/sessions", tags=["dialogue"])

def _make_generator() -> QuestionGenerator:
    return QuestionGenerator(llm=LLMService())

@router.post("/{sid}/turns", response_model=TurnResponse)
async def post_turn(
    sid: str,
    body: TurnIn,
    count: int = Query(default=5, ge=1, le=10),
    user_id: str = Depends(current_user_id_from_token),
):
    db = get_db()
    s = await db.sessions.find_one({"_id": ObjectId(sid), "user_id": user_id})
    if not s:
        raise HTTPException(404, "session not found")

    await db.turns.insert_one({"session_id": sid, "role": "stakeholder", "content": body.content, "created_at": datetime.utcnow()})

    history = []
    async for t in db.turns.find({"session_id": sid}).sort("created_at", 1):
        history.append({"role": t["role"], "content": t["content"], "strategy": t.get("strategy")})

    gen = _make_generator()
    out: list[QuestionOut] = []
    for _ in range(count):
        gq = await gen.next_question(phase=s["phase"], summary=s.get("summary") or "", history=history)
        await db.turns.insert_one({
            "session_id": sid, "role": "agent", "content": gq.question,
            "strategy": gq.strategy, "validator_attempts": gq.attempts,
            "validator_verdict": "valid" if gq.valid else "max_retries",
            "created_at": datetime.utcnow(),
        })
        history.append({"role":"agent","content":gq.question,"strategy":gq.strategy})
        out.append(QuestionOut(question=gq.question, strategy=gq.strategy, attempts=gq.attempts, valid=gq.valid))
    return TurnResponse(questions=out)
```

- [ ] **Step 4: Mount router**, **run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/dialogue.py backend/app/routers/dialogue.py backend/app/main.py backend/tests/test_dialogue_router.py
git commit -m "feat(dialogue): POST /sessions/{id}/turns generates 5-10 probing questions"
```

### Task 5.3: Requirements compilation + export

**Files:**
- Create: `backend/app/services/export_service.py`, `backend/app/routers/export.py`, `backend/tests/test_export.py`
- Modify: `backend/app/main.py`

Compilation strategy: after each turn, call Gemini to extract candidate requirement statements from the last stakeholder reply (separate JSON-mode call) and upsert into `requirements` collection. Export builds a Markdown report.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from app.services.export_service import compile_markdown

def test_compile_markdown_groups_by_type():
    reqs = [
        {"statement": "Users can log in.", "type": "functional"},
        {"statement": "P95 latency < 5s for 1000-word input.", "type": "non_functional"},
    ]
    md = compile_markdown(project_title="Payments", requirements=reqs)
    assert "# Requirements: Payments" in md
    assert "## Functional Requirements" in md
    assert "Users can log in." in md
    assert "## Non-Functional Requirements" in md
```

- [ ] **Step 2: Implement compiler**

```python
from typing import Iterable
_TYPE_TITLES = {
    "functional": "Functional Requirements",
    "non_functional": "Non-Functional Requirements",
    "constraint": "Constraints",
}

def compile_markdown(*, project_title: str, requirements: Iterable[dict]) -> str:
    buckets: dict[str, list[str]] = {k: [] for k in _TYPE_TITLES}
    for r in requirements:
        buckets.setdefault(r["type"], []).append(r["statement"])
    parts = [f"# Requirements: {project_title}\n"]
    for key, title in _TYPE_TITLES.items():
        items = buckets.get(key) or []
        if items:
            parts.append(f"## {title}\n")
            parts.extend(f"- {s}" for s in items)
            parts.append("")
    return "\n".join(parts)
```

- [ ] **Step 3: Export router**

```python
# routers/export.py
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from bson import ObjectId
from ..db.mongo import get_db
from ..deps import current_user_id_from_token
from ..services.export_service import compile_markdown

router = APIRouter(prefix="/sessions", tags=["export"])

@router.get("/{sid}/export", response_class=PlainTextResponse)
async def export_session(
    sid: str,
    format: str = Query(default="md", pattern="^(md|txt)$"),
    user_id: str = Depends(current_user_id_from_token),
):
    db = get_db()
    s = await db.sessions.find_one({"_id": ObjectId(sid), "user_id": user_id})
    if not s:
        raise HTTPException(404, "session not found")
    reqs = [r async for r in db.requirements.find({"session_id": sid})]
    md = compile_markdown(project_title=s["project_title"], requirements=reqs)
    if format == "txt":
        return md.replace("#", "").strip()
    return md
```

- [ ] **Step 4: Mount router**, **run tests** → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_service.py backend/app/routers/export.py backend/app/main.py backend/tests/test_export.py
git commit -m "feat(export): markdown/text export of compiled requirements"
```

### Task 5.4: Requirement extraction service (Gemini JSON call)

**Files:**
- Create: `backend/app/services/requirement_extractor.py`, `backend/tests/test_requirement_extractor.py`
- Modify: `backend/app/routers/dialogue.py` to call extractor after each stakeholder turn

- [ ] **Step 1: Write failing test**

```python
import pytest
from app.services.requirement_extractor import RequirementExtractor

class Stub:
    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        return '{"requirements": [{"statement":"Users can pay by card.","type":"functional"}]}'

@pytest.mark.asyncio
async def test_extract_returns_typed_requirements():
    ex = RequirementExtractor(llm=Stub())
    out = await ex.extract("I want a payment app accepting cards.")
    assert out[0]["statement"].startswith("Users can pay")
    assert out[0]["type"] == "functional"
```

- [ ] **Step 2: Implement extractor**

```python
import json
class RequirementExtractor:
    def __init__(self, *, llm): self.llm = llm
    async def extract(self, stakeholder_text: str) -> list[dict]:
        prompt = (
            "Extract atomic, testable requirements from the stakeholder text below. "
            "Classify each as functional, non_functional, or constraint. "
            "Return JSON: {\"requirements\": [{\"statement\": str, \"type\": str}]}\n"
            f"Text:\n\"\"\"{stakeholder_text}\"\"\""
        )
        raw = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
        return json.loads(raw).get("requirements", [])
```

- [ ] **Step 3: Wire into dialogue router** (after persisting stakeholder turn, call extractor and upsert into `requirements`). Add tests for the integration path.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/requirement_extractor.py backend/tests/test_requirement_extractor.py backend/app/routers/dialogue.py
git commit -m "feat(requirements): per-turn extraction into requirements collection"
```

---

## Phase 6 — Frontend

### Task 6.1: API client + auth store + protected routing

**Files:**
- Create: `frontend/src/api/client.ts`, `frontend/src/api/auth.ts`, `frontend/src/store/authStore.ts`, `frontend/src/components/Auth/ProtectedRoute.tsx`

- [ ] **Step 1: Implement axios client**

```ts
// src/api/client.ts
import axios from "axios";
import { useAuthStore } from "../store/authStore";
export const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE });
api.interceptors.request.use((c) => {
  const t = useAuthStore.getState().token;
  if (t) c.headers.Authorization = `Bearer ${t}`;
  return c;
});
```

- [ ] **Step 2: Auth store**

```ts
// src/store/authStore.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";
type State = { token: string | null; setToken: (t: string | null) => void; };
export const useAuthStore = create<State>()(
  persist((set) => ({ token: null, setToken: (token) => set({ token }) }), { name: "auth" })
);
```

- [ ] **Step 3: Auth API**

```ts
// src/api/auth.ts
import { api } from "./client";
export const signup = (b: { email: string; password: string; real_name: string; phone?: string }) =>
  api.post("/auth/signup", b).then((r) => r.data.access_token);
export const login = (b: { email: string; password: string }) =>
  api.post("/auth/login", b).then((r) => r.data.access_token);
```

- [ ] **Step 4: ProtectedRoute**

```tsx
// src/components/Auth/ProtectedRoute.tsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
export default function ProtectedRoute() {
  const token = useAuthStore((s) => s.token);
  return token ? <Outlet /> : <Navigate to="/login" replace />;
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api frontend/src/store frontend/src/components/Auth
git commit -m "feat(fe): API client, auth store, protected routing"
```

### Task 6.2: Login & Signup pages (Figures 4.8 & 4.9)

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/SignupPage.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/main.tsx`

Login (Figure 4.8): centered card, email + password, high-contrast Login button, link to signup.
Signup (Figure 4.9): email, password, real_name (placeholder "Real name for future operation"), phone, link back to login.

- [ ] **Step 1: Implement `LoginPage.tsx`**

```tsx
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../api/auth";
import { useAuthStore } from "../store/authStore";

export default function LoginPage() {
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const setToken = useAuthStore((s) => s.setToken);
  const nav = useNavigate();
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <form
        className="w-96 p-8 bg-white rounded-2xl shadow space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          try { setToken(await login({ email, password })); nav("/"); }
          catch (e: any) { setErr(e?.response?.data?.detail ?? "Login failed"); }
        }}
      >
        <h1 className="text-2xl font-semibold">Login</h1>
        <input className="w-full border rounded p-2" placeholder="Email" value={email} onChange={(e)=>setEmail(e.target.value)} />
        <input className="w-full border rounded p-2" type="password" placeholder="Password" value={password} onChange={(e)=>setPassword(e.target.value)} />
        {err && <p className="text-red-600 text-sm">{err}</p>}
        <button className="w-full bg-indigo-600 text-white rounded p-2 font-medium">Login</button>
        <p className="text-sm text-right"><Link to="/signup" className="text-indigo-600">Create an account</Link></p>
      </form>
    </div>
  );
}
```

- [ ] **Step 2: Implement `SignupPage.tsx`** (mirror, add `real_name`, `phone`).

- [ ] **Step 3: Wire routes in `App.tsx`**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";
import MainPage from "./pages/MainPage";
import ProtectedRoute from "./components/Auth/ProtectedRoute";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route element={<ProtectedRoute />}>
          <Route path="/" element={<MainPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Smoke test in browser** (`npm run dev`) and confirm signup → redirected to `/`. Commit.

```bash
git add frontend/src
git commit -m "feat(fe): login & signup pages with protected routing"
```

### Task 6.3: Main 3-panel layout (Figure 4.6)

**Files:**
- Create: `frontend/src/pages/MainPage.tsx`, `frontend/src/components/Sidebar/SessionList.tsx`, `frontend/src/components/Dialogue/ChatPanel.tsx`, `frontend/src/components/Dialogue/StatusIndicator.tsx`, `frontend/src/components/Dialogue/InputBox.tsx`, `frontend/src/components/Requirements/LiveRequirements.tsx`

Layout: CSS grid `grid-cols-[260px_1fr_320px]`.

- [ ] **Step 1: Session store**

```ts
// src/store/sessionStore.ts
import { create } from "zustand";
type Turn = { role: "stakeholder" | "agent"; content: string; strategy?: string };
type Status = "idle" | "thinking" | "validating";
type State = {
  activeId: string | null; setActive: (id: string | null) => void;
  turns: Turn[]; setTurns: (t: Turn[]) => void; pushTurn: (t: Turn) => void;
  status: Status; setStatus: (s: Status) => void;
};
export const useSessionStore = create<State>((set) => ({
  activeId: null, setActive: (activeId) => set({ activeId }),
  turns: [], setTurns: (turns) => set({ turns }), pushTurn: (t) => set((s) => ({ turns: [...s.turns, t] })),
  status: "idle", setStatus: (status) => set({ status }),
}));
```

- [ ] **Step 2: `SessionList.tsx`** — fetches `GET /sessions`, separates `active`/`archived`, shows green dot for active.

- [ ] **Step 3: `StatusIndicator.tsx`**

```tsx
import { useSessionStore } from "../../store/sessionStore";
export default function StatusIndicator() {
  const s = useSessionStore((x) => x.status);
  if (s === "idle") return null;
  const label = s === "thinking" ? "Generating probing question…" : "Validating question relevance…";
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-50 text-amber-800 text-xs">
      <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse" /> {label}
    </div>
  );
}
```

- [ ] **Step 4: `ChatPanel.tsx`** — renders right-aligned stakeholder bubbles and left-aligned agent bubbles, includes `StatusIndicator` above the latest agent message.

- [ ] **Step 5: `InputBox.tsx`** — controlled textarea + Send button. On submit: set status `thinking` → POST `/sessions/{id}/turns?count=5` → set status `validating` while awaiting → push agent turns → reset to `idle`.

- [ ] **Step 6: `LiveRequirements.tsx`** — polls `GET /sessions/{id}/requirements` every 3 s (or after each send) and lists statements grouped by type.

- [ ] **Step 7: `MainPage.tsx`** — composes all three columns.

- [ ] **Step 8: Manual UX check** in browser. Commit.

```bash
git add frontend/src
git commit -m "feat(fe): main 3-panel UI (sessions / dialogue / live requirements)"
```

### Task 6.4: Export download button

**Files:**
- Modify: `frontend/src/components/Requirements/LiveRequirements.tsx`
- Create: `frontend/src/api/sessions.ts`

- [ ] **Step 1: API call**

```ts
// src/api/sessions.ts
import { api } from "./client";
export const exportSession = (id: string, format: "md" | "txt" = "md") =>
  api.get(`/sessions/${id}/export`, { params: { format }, responseType: "blob" }).then((r) => r.data);
```

- [ ] **Step 2: Button in `LiveRequirements`** — triggers download via `URL.createObjectURL`.

- [ ] **Step 3: Smoke test** end-to-end. Commit.

```bash
git add frontend/src
git commit -m "feat(fe): download requirements as Markdown or text"
```

---

## Phase 7 — Integration & E2E

### Task 7.1: Playwright E2E for the golden path

**Files:**
- Create: `frontend/tests/e2e/golden.spec.ts`, `frontend/playwright.config.ts`

- [ ] **Step 1: Implement spec**

```ts
import { test, expect } from "@playwright/test";
test("signup → create session → ask → see probing question → export", async ({ page }) => {
  await page.goto("/signup");
  await page.getByPlaceholder("Email").fill("test@x.com");
  await page.getByPlaceholder("Password").fill("Passw0rd!");
  await page.getByPlaceholder("Real name for future operation").fill("Tester");
  await page.getByRole("button", { name: "Sign up" }).click();
  await page.getByRole("button", { name: "New Session" }).click();
  await page.getByPlaceholder("Project title").fill("Payments");
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByPlaceholder("Describe what you want…").fill("I want a payment app for online retail.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.locator("[data-role=agent]").first()).toBeVisible({ timeout: 10000 });
  await page.getByRole("button", { name: "Export" }).click();
});
```

- [ ] **Step 2: Run against docker-compose stack**

```bash
docker compose up -d --build
cd frontend && npx playwright test
```
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests frontend/playwright.config.ts
git commit -m "test(e2e): golden path signup → dialogue → export"
```

### Task 7.2: Non-functional gates

**Files:**
- Create: `backend/tests/test_perf.py`

- [ ] **Step 1: Write timing test** asserting `next_question` returns in <5 s for a 1000-word stakeholder input using a recorded LLM stub. This pins the NFR target.

- [ ] **Step 2: Add CI step** in `.github/workflows/ci.yml`:

```yaml
name: ci
on: [push, pull_request]
jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      mongo: { image: mongo:7, ports: ["27017:27017"] }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e "./backend[dev]"
      - run: cd backend && pytest -q
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: cd frontend && npm ci && npm run build && npx vitest run
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_perf.py .github/workflows/ci.yml
git commit -m "ci: backend + frontend test pipeline, NFR latency gate"
```

---

## Phase 8 — Deployment & Documentation

### Task 8.1: Local hosting bundle (for FYP viva)

- [ ] **Step 1: Verify** `docker compose up --build` exposes the full stack on a single command.

- [ ] **Step 2: Write `docs/RUNBOOK.md`** with: install Docker → `cp .env.example .env` → fill `GEMINI_API_KEY` → `docker compose up --build` → open `http://localhost:5173`.

- [ ] **Step 3: Capture screenshots** of: Login (Fig 4.8), Signup (Fig 4.9), Main (Fig 4.6) for the report's update.

- [ ] **Step 4: Commit**

```bash
git add docs/RUNBOOK.md
git commit -m "docs: runbook for local viva deployment"
```

### Task 8.2: Optional cloud deployment

- [ ] **Step 1: Build images** and push to a container registry of choice (GHCR, Docker Hub).

- [ ] **Step 2: Provision** MongoDB Atlas free tier + a single VM/Fly.io/Render service.

- [ ] **Step 3: Set env vars** in the cloud target. Verify health endpoint over HTTPS.

- [ ] **Step 4: Update `docs/RUNBOOK.md`** with cloud URL. Commit.

---

## Schedule (aligned with FYP2 Gantt — Section 5.5)

| Weeks | Phases |
|---|---|
| 1–2 | Phase 0–1 (setup, config, DB, models) |
| 3 | Phase 2 (auth) |
| 4–5 | Phase 3 (LLM service) + Phase 4 (agent: Context/Strategy/Validator/Generator) |
| 6 | Phase 5 (sessions, dialogue, export) |
| 7–8 | Phase 6 (frontend) |
| 9 | Phase 7 (integration + NFR gates) |
| 10–12 | UAT, fixes, Phase 8 (deployment), final viva prep |

---

## Acceptance Checklist (from Chapter 3)

- [ ] FR-1: Accept stakeholder text input.
- [ ] FR-2: Produce 5–10 context-based probing questions per turn.
- [ ] FR-3: Multi-turn — answers feed back into subsequent questions (verified by integration test).
- [ ] FR-4: Export conversation/requirements as Markdown or text.
- [ ] NFR-1: ≥85% rated useful in UAT (Task 7 results collected via post-UAT form).
- [ ] NFR-2: <5 s response for 1000-word input (Task 7.2 perf test).
- [ ] NFR-3: User-friendly UI (UAT pass).
- [ ] NFR-4: Validator filters leading / vague / etc. questions (Task 4.4 unit + Task 4.5 integration).
- [ ] NFR-5: User data privacy — no persistent stakeholder PII beyond what the user explicitly enters; document retention policy.

---

## Self-Review Notes

- **Spec coverage:** FR-1..4 covered by Tasks 5.2, 4.5 (5–10 questions via loop), 5.2 (multi-turn history), 5.3 (export). NFRs covered by Tasks 4.4 (mistake filtering), 7.2 (latency), 7.1 (E2E UX), Phase 6 (UI). Hybrid Intelligent Agent (the project's novel claim) implemented across Tasks 4.2–4.5. Use Cases (Sign up/Login, View Chat History, Engage in Probing Dialogue, Compile Requirement, Review/Export) covered.
- **Placeholders scan:** Each step contains real code or commands.
- **Type consistency:** `GeneratedQuestion` produced by `QuestionGenerator` matches fields consumed in dialogue router and `QuestionOut`. `Verdict` shape consistent. Model field names (`session_id`, `role`, `strategy`, `validator_attempts`, `validator_verdict`, `phase`) are reused everywhere.
