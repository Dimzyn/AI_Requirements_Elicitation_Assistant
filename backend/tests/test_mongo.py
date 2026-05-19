import pytest
from app.db.mongo import get_db, init_indexes

@pytest.mark.asyncio
async def test_get_db_returns_database():
    db = get_db()
    assert db.name

@pytest.mark.asyncio
async def test_init_indexes_runs():
    await init_indexes()
