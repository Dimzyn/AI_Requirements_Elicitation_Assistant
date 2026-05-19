import pytest
from mongomock_motor import AsyncMongoMockClient

from app.db import mongo as mongo_mod


@pytest.fixture(autouse=True)
def patch_mongo(monkeypatch):
    mock_client = AsyncMongoMockClient()
    monkeypatch.setattr(mongo_mod, "_client", mock_client)
    yield
