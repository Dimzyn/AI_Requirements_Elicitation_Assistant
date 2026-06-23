import pytest
from app.db.mongo import init_indexes, get_db


@pytest.mark.asyncio
async def test_init_indexes_creates_new_collections():
    await init_indexes()
    db = get_db()
    member_idx = await db.memberships.index_information()
    invite_idx = await db.invitations.index_information()
    sess_idx = await db.sessions.index_information()
    def keys_of(idx):
        return tuple(k for k, _ in idx["key"])
    assert any(keys_of(v) == ("project_id", "user_id") and v.get("unique") for v in member_idx.values())
    assert any(keys_of(v) == ("token",) and v.get("unique") for v in invite_idx.values())
    # The (project_id, stakeholder_id) uniqueness MUST be partial to interview sessions,
    # otherwise auto-created conflict-resolution chats collide on a duplicate key.
    assert any(
        keys_of(v) == ("project_id", "stakeholder_id")
        and v.get("unique")
        and v.get("partialFilterExpression") == {"kind": "interview"}
        for v in sess_idx.values()
    )
