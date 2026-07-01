import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Surface app-level INFO logs (question timing, Gemini fallback events) in the
# console; uvicorn only configures its own loggers, not the root, by default.
logging.basicConfig(level=logging.INFO)

from .config import settings
from .db.mongo import init_indexes
from .routers import auth as auth_router
from .routers import sessions as sessions_router
from .routers import dialogue as dialogue_router
from .routers import export as export_router
from .routers import requirements as requirements_router
from .routers import projects as projects_router
from .routers import invitations as invitations_router
from .routers import conflicts as conflicts_router

app = FastAPI(title="AI Probing Question Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router.router)
app.include_router(sessions_router.router)
app.include_router(dialogue_router.router)
app.include_router(export_router.router)
app.include_router(export_router.projects_router)
app.include_router(requirements_router.router)
app.include_router(projects_router.router)
app.include_router(invitations_router.router)
app.include_router(conflicts_router.router)


@app.on_event("startup")
async def _startup():
    await init_indexes()


@app.get("/health")
def health():
    return {"status": "ok"}
