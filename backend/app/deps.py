from bson import ObjectId
from fastapi import Depends, Header, HTTPException, status

from .db.mongo import get_db
from .services.auth_service import decode_token


def current_user_id_from_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = decode_token(authorization.split(" ", 1)[1])
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no subject")
    return sub


async def current_user_doc(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = decode_token(authorization.split(" ", 1)[1])
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no subject")
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(sub)})
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    user["_id"] = str(user["_id"])
    return user


async def require_engineer(user: dict = Depends(current_user_doc)) -> dict:
    if user.get("role") != "requirements_engineer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires requirements_engineer role")
    return user


async def require_stakeholder(user: dict = Depends(current_user_doc)) -> dict:
    if user.get("role") != "stakeholder":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "requires stakeholder role")
    return user
