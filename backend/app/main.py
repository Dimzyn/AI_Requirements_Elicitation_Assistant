from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db.mongo import init_indexes
from .routers import auth as auth_router

app = FastAPI(title="AI Probing Question Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router.router)


@app.on_event("startup")
async def _startup():
    await init_indexes()


@app.get("/health")
def health():
    return {"status": "ok"}
