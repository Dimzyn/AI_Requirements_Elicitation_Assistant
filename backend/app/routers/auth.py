from fastapi import APIRouter, HTTPException, status
from ..db.mongo import get_db
from ..schemas.auth import SignupRequest, LoginRequest, TokenResponse
from ..services.auth_service import hash_password, verify_password, create_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/signup", status_code=201, response_model=TokenResponse)
async def signup(body: SignupRequest):
    db = get_db()
    if await db.users.find_one({"email": body.email}):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")
    doc = {
        "email": body.email,
        "hashed_password": hash_password(body.password),
        "real_name": body.real_name,
        "phone": body.phone,
        "domain_level": "novice",
    }
    res = await db.users.insert_one(doc)
    return TokenResponse(access_token=create_token({"sub": str(res.inserted_id)}))

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    db = get_db()
    user = await db.users.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return TokenResponse(access_token=create_token({"sub": str(user["_id"])}))
