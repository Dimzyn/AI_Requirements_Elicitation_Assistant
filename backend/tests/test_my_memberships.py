import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from tests.helpers import _re_project_and_invited_stakeholder


@pytest.mark.asyncio
async def test_stakeholder_lists_member_projects():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        reh, sh, pid = await _re_project_and_invited_stakeholder(c)
        r = await c.get("/projects/mine/memberships", headers=sh)
        assert r.status_code == 200
        assert [p["id"] for p in r.json()] == [pid]
