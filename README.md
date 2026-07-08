# FYPver2 — AI Requirements Elicitation Assistant

An AI-powered requirements elicitation tool. It runs adaptive stakeholder interviews
(generating probing questions with Google Gemini), extracts software requirements,
detects cross-stakeholder conflicts, opens AI-guided conflict-resolution chats, and
exports an IEEE-830-style SRS.

**Stack:** React 19 + TypeScript + Vite + Zustand + Tailwind (frontend) · FastAPI +
MongoDB (Motor) + Pydantic v2 (backend) · JWT auth · Docker Compose · pytest + Vitest.

## Services & ports

| Service  | URL / Port            | Notes                                       |
| -------- | --------------------- | ------------------------------------------- |
| Frontend | http://localhost:5173 | nginx serving the built SPA (baked image)   |
| Backend  | http://localhost:8000 | FastAPI; docs at `/docs`, health at `/health` |
| MongoDB  | `localhost:27017`     | data persisted in the `mongo_data` volume   |

---

## Quick start (Docker)

> Requires **Docker Desktop running**.

1. Create your env file, then set a Gemini API key and a JWT secret:
   ```bash
   cp .env.example .env
   # edit .env: set GEMINI_API_KEY and JWT_SECRET
   ```
2. Build and start the stack:
   ```bash
   docker compose up -d --build
   ```
3. Open **http://localhost:5173** and sign up. The first account is a *stakeholder* —
   see [Roles & onboarding](#roles--onboarding) to make it a Requirements Engineer.

### Environment variables (`.env`)

| Variable                 | Example                  | Purpose                                   |
| ------------------------ | ------------------------ | ----------------------------------------- |
| `MONGO_URI`              | `mongodb://mongo:27017`  | Mongo connection (service name on the compose network) |
| `MONGO_DB`               | `probing`                | Database name                             |
| `JWT_SECRET`             | `replace-me`             | **Change this** — signs auth tokens       |
| `JWT_ALG` / `JWT_TTL_MINUTES` | `HS256` / `60`      | Token algorithm / lifetime                |
| `GEMINI_API_KEY`         | `AIza...`                | **Required** — Google Gemini key          |
| `GEMINI_MODEL`           | `gemini-2.5-flash`       | Primary question/extraction model         |
| `GEMINI_VALIDATOR_MODEL` | `gemini-2.5-flash`       | Validator model                           |
| `CORS_ORIGINS`           | `http://localhost:5173`  | Allowed frontend origin                   |
| `VITE_API_BASE`          | `http://localhost:8000`  | Backend base URL the frontend calls       |

> ⚠️ Never commit a real `GEMINI_API_KEY` or `JWT_SECRET`. Keep them in `.env` (which
> should be git-ignored); use `.env.example` for placeholders only.

---

## Roles & onboarding

The app has two roles: **Requirements Engineer (RE)** and **Stakeholder**.

- **Every new signup is a stakeholder.** There is intentionally no in-app way to
  self-promote to RE.
- **Promote a user to RE** (run inside the backend container, which can reach Mongo):
  ```bash
  docker compose exec backend python -m scripts.promote_user you@example.com
  ```
  Then **refresh the page or log out/in** — the frontend re-reads the role from
  `/auth/me` and switches to the engineer view. Verify with:
  ```bash
  docker compose exec mongo mongosh probing --quiet \
    --eval 'db.users.findOne({email:"you@example.com"},{email:1,role:1})'
  ```
- The RE creates a **project**, sets its background/goals (used as AI context), and
  invites stakeholders by email.
- Email is **not** sent automatically (current scope): the invite link is shown on the
  RE's project page — copy and share it manually. *(Future work: automatic email delivery.)*
- The stakeholder opens the invite link, sets a password, and lands in their interview
  for that project. Each stakeholder has one interview session per project.
- **Ending elicitation:** when the interview stops surfacing new requirements, the
  assistant suggests wrapping up; the stakeholder can mark themselves **done**, which
  flags the session *Ready for review* for the RE. The RE then confirms by marking the
  session **ended**, after which the stakeholder sees an end-of-interview banner and
  can no longer send.
- The RE reviews sessions per project (Projects → project detail), runs **conflict
  detection**, can request **AI-suggested reconciled wording** for a conflict (and
  approve/edit it), curates requirements on the spec page (conflicted rows are
  highlighted), and exports the **SRS**.

---

## Common commands (cheat sheet)

### Docker

```bash
# Refresh: rebuild images and recreate containers (use after code changes)
docker compose up -d --build

# Rebuild & recreate ONE service (e.g. after frontend changes — it's a baked image)
docker compose up -d --build frontend
docker compose up -d --build backend

# Status of the stack
docker compose ps

# Tail logs (all services, or one)
docker compose logs -f
docker compose logs -f backend

# Restart a service without rebuilding
docker compose restart backend

# Stop containers (keeps data + images)
docker compose stop

# Stop and remove containers + network (KEEPS the mongo_data volume)
docker compose down

# Full reset — also DELETES the database volume (irreversible)
docker compose down -v
```

> The backend live-mounts `./backend/app`, so most backend code changes are picked up
> on container restart. The **frontend is a baked production image** with no mount —
> always rebuild it (`--build frontend`) to see UI changes.

> If Docker fails with *"cannot connect to the Docker daemon"*, start **Docker Desktop**
> first and wait for the engine to come up.

### Tests

Backend (uses the project virtualenv at `backend/.venv`):

```bash
cd backend && .\.venv\Scripts\python.exe -m pytest -q     # Windows
# cd backend && .venv/bin/python -m pytest -q             # macOS / Linux
```

Frontend:

```bash
cd frontend
npm run build      # tsc type-check + vite production build
npm test           # vitest run (node-env unit tests; Playwright owns the browser path)
```

End-to-end (Playwright, Chromium) — expects the app already running at
`http://localhost:5173` (e.g. via `docker compose up -d`):

```bash
cd frontend
npx playwright test               # override target with E2E_BASE_URL=<url>
```

---

## Local development (without Docker)

You need a reachable MongoDB and a `.env` whose `MONGO_URI` points to it
(e.g. `mongodb://localhost:27017`).

```bash
# Backend
cd backend
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000   # Windows
# .venv/bin/python -m uvicorn app.main:app --reload --port 8000          # macOS/Linux

# Frontend (Vite dev server with HMR)
cd frontend
npm install
npm run dev        # http://localhost:5173
```

---

## Project structure

```
.
├── docker-compose.yml        # mongo + backend + frontend
├── .env / .env.example       # backend + frontend config
├── backend/
│   ├── app/                  # FastAPI app (routers, services, schemas, models)
│   ├── scripts/              # ops scripts (e.g. promote_user.py)
│   └── tests/                # pytest suite
└── frontend/
    ├── src/                  # React app (pages, components, stores, api) + colocated unit tests
    └── tests/e2e/            # Playwright end-to-end suite
```

---

## Troubleshooting

- **New account shows another user's chat history** — fixed; the client wipes
  user-scoped stores on login/logout/signup/invite-accept. If it persists on an old
  tab, hard-refresh.
- **`docker compose exec` says the service isn't running** — start the stack first
  with `docker compose up -d`.
- **Gemini 429 / 503 in the UI** — the API is rate-limited or overloaded; the backend
  retries and falls back to a secondary model, then surfaces a "try again" message.
