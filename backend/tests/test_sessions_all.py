import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from tests.helpers import _re_project_and_invited_stakeholder


@pytest.mark.asyncio
async def test_re_sees_all_sessions_in_owned_projects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        await c.post(f"/projects/{pid}/session", headers=sh)
        r = await c.get("/sessions/all", headers=reh)
        assert r.status_code == 200
        assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_stakeholder_cannot_list_all_sessions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        r = await c.get("/sessions/all", headers=sh)
        assert r.status_code == 403
