from datetime import datetime, timedelta, timezone
from jose import jwt
from passlib.context import CryptContext
from ..config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return _pwd.hash(p)

def verify_password(p: str, hashed: str) -> bool:
    return _pwd.verify(p, hashed)

def create_token(sub_claims: dict) -> str:
    payload = {
        **sub_claims,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_ttl_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)

def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
