import pytest
from fastapi import HTTPException
from app.deps import require_engineer, require_stakeholder


@pytest.mark.asyncio
async def test_require_engineer_allows_re():
    user = {"_id": "u1", "role": "requirements_engineer"}
    assert await require_engineer(user=user) is user


@pytest.mark.asyncio
async def test_require_engineer_rejects_stakeholder():
    with pytest.raises(HTTPException) as exc:
        await require_engineer(user={"_id": "u1", "role": "stakeholder"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_stakeholder_rejects_re():
    with pytest.raises(HTTPException) as exc:
        await require_stakeholder(user={"_id": "u1", "role": "requirements_engineer"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_stakeholder_allows_stakeholder():
    user = {"_id": "u1", "role": "stakeholder"}
    assert await require_stakeholder(user=user) is user
