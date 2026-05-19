# Runbook: AI Probing Question Generator

Local hosting guide for the FYP viva. The stack is a FastAPI backend, a MongoDB 7 instance, and a Vite/React frontend served by nginx — all orchestrated by Docker Compose.

## Prerequisites

- Docker Desktop 4.x or Docker Engine 24.x with the Compose v2 plugin.
- A Google Gemini API key (`GEMINI_API_KEY`). See https://ai.google.dev for issuance.
- 4 GB free RAM (Mongo + backend + frontend containers).
- Open ports on the host: `27017`, `8000`, `5173`.

## First-run setup

From the repo root (`D:/Program Files/githubsof/FYPver2`):

```bash
cp .env.example .env
# edit .env and set GEMINI_API_KEY to your real key
# also change JWT_SECRET to any long random string before exposing the stack to a network
docker compose up --build
```

The first build takes ~3 minutes (Python deps + npm install). Subsequent starts use cached layers and come up in <30 s.

Once you see `Uvicorn running on http://0.0.0.0:8000` and `Vite ready in ... ms`, open:

- Frontend UI: http://localhost:5173
- Backend OpenAPI docs: http://localhost:8000/docs
- Backend health probe: http://localhost:8000/health

## Day-to-day commands

| Action | Command |
|---|---|
| Start (foreground, with logs) | `docker compose up` |
| Start (background) | `docker compose up -d` |
| Stop | `docker compose down` |
| Stop **and** wipe the Mongo volume | `docker compose down -v` |
| Tail backend logs | `docker compose logs -f backend` |
| Run backend tests | `docker compose exec backend pytest -q` |
| Rebuild after dependency change | `docker compose up --build` |

## Configuration reference

All settings live in `.env` (created from `.env.example`):

| Variable | Default | Notes |
|---|---|---|
| `MONGO_URI` | `mongodb://mongo:27017` | Container DNS resolves `mongo` to the DB service. |
| `MONGO_DB` | `probing` | Logical DB name. |
| `JWT_SECRET` | `replace-me` | Pick a long random value before exposing externally. |
| `JWT_ALG` | `HS256` | Don't change unless you're also changing the verifier. |
| `JWT_TTL_MINUTES` | `60` | Token lifetime. |
| `GEMINI_API_KEY` | _(empty)_ | Required. Backend startup logs a clear error if missing. |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Drafting model. |
| `GEMINI_VALIDATOR_MODEL` | `gemini-2.5-flash` | Validator model. Set to `gemini-2.5-pro` for stricter validation at higher cost. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated list for browser origins. |
| `VITE_API_BASE` | `http://localhost:8000` | Build-time variable baked into the frontend bundle. |

## Smoke-test the golden path

1. Browse to http://localhost:5173 — you'll be redirected to `/login`.
2. Click "Create an account" and sign up with any email + password + real name.
3. Click "New Session", give it a project title (e.g. "Online Pharmacy"), click "Create".
4. Type a vague description into the input box (e.g. `I want a pharmacy app where patients can refill prescriptions and chat with a pharmacist.`).
5. Click "Send". The status pill shows "Generating…" then "Validating…" while the agent produces 5 probing questions.
6. Verify the right rail lists extracted requirements grouped by Functional / Non-Functional / Constraint.
7. Click `.md` in the top of the right rail to download the requirements report.

## End-to-end test (optional)

The Playwright spec at `frontend/tests/e2e/golden.spec.ts` exercises the same path automatically. With the stack running:

```bash
cd frontend
npx playwright install chromium
npx playwright test
```

Set `E2E_BASE_URL` to point at a different host if not running on the default port.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `400` on signup | password too short | Use ≥8 chars. |
| Backend 401 on every call | JWT expired or store cleared | Log out + back in. |
| Indefinite "Validating…" | Gemini API key invalid or quota exhausted | Verify key + quota in Google AI Studio. |
| Empty live-requirements panel | Stakeholder reply was too vague for extraction | Type a more concrete description and resend. |
| `MongoDB connection refused` on backend startup | `mongo` service still starting | Wait 5 s and refresh; Compose retry will reconnect. |

## Resetting state

```bash
docker compose down -v   # wipes user accounts, sessions, turns, requirements
docker compose up --build
```

## Updating without losing data

```bash
git pull
docker compose up --build   # rebuild image layers, Mongo volume persists
```
