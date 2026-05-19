import pytest
from app.services.auth_service import hash_password, verify_password, create_token, decode_token

def test_hash_roundtrip():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h)
    assert not verify_password("wrong", h)

def test_token_roundtrip():
    tok = create_token({"sub": "user-123"})
    claims = decode_token(tok)
    assert claims["sub"] == "user-123"
