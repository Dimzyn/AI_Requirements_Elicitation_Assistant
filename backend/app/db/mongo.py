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
    # One *interview* session per (project, stakeholder). Conflict-resolution chats are
    # ADDITIONAL sessions for the same pair, so this uniqueness is PARTIAL (kind=interview)
    # — a plain unique index rejects every resolution chat with a duplicate-key error.
    # Migrate the old non-partial index from earlier deployments before (re)creating it.
    sess_info = await db.sessions.index_information()
    legacy = sess_info.get("project_id_1_stakeholder_id_1")
    if legacy is not None and "partialFilterExpression" not in legacy:
        await db.sessions.drop_index("project_id_1_stakeholder_id_1")
    await db.sessions.create_index(
        [("project_id", 1), ("stakeholder_id", 1)],
        unique=True,
        partialFilterExpression={"kind": "interview"},
    )
    await db.sessions.create_index([("stakeholder_id", 1), ("status", 1)])
    await db.turns.create_index([("session_id", 1), ("created_at", 1)])
    await db.requirements.create_index("session_id")
    await db.requirements.create_index("status")
    await db.projects.create_index("owner_id")
    await db.memberships.create_index([("project_id", 1), ("user_id", 1)], unique=True)
    await db.invitations.create_index("token", unique=True)
    await db.invitations.create_index([("project_id", 1), ("email", 1)])
    await db.conflicts.create_index([("project_id", 1), ("pair_key", 1)], unique=True)
    await db.conflicts.create_index([("project_id", 1), ("status", 1)])
