# The old session endpoints (POST /sessions, archive/unarchive/delete) have been removed
# as part of the project-scoped session migration (Phase 5).
# All session behaviour is now tested in test_sessions_project_scope.py.
#
# This file keeps a minimal smoke test so that the 401 guard on the
# still-present /sessions (list-my) and /sessions/{sid}/complete routes works.

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_list_my_sessions_401_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/sessions")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_complete_session_401_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/sessions/507f1f77bcf86cd799439011/complete")
        assert r.status_code == 401
