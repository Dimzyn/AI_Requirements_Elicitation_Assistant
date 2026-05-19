import pytest
from fastapi import HTTPException
from app.deps import current_user_id_from_token
from app.services.auth_service import create_token

def test_valid_token_returns_sub():
    tok = create_token({"sub": "u1"})
    assert current_user_id_from_token(f"Bearer {tok}") == "u1"

def test_missing_bearer_raises():
    with pytest.raises(HTTPException):
        current_user_id_from_token(None)
