from typing import Optional

from pydantic import BaseModel, EmailStr


class ProjectCreate(BaseModel):
    title: str
    background: Optional[str] = None
    goals: Optional[str] = None
    scope: Optional[str] = None


class ProjectOut(BaseModel):
    id: str
    title: str
    background: Optional[str] = None
    goals: Optional[str] = None
    scope: Optional[str] = None
    created_at: Optional[str] = None


class MemberOut(BaseModel):
    user_id: str
    email: str
    real_name: str
    joined_at: Optional[str] = None


class InviteCreate(BaseModel):
    email: EmailStr


class InviteOut(BaseModel):
    id: str
    email: str
    status: str
    token: str
    accept_url: str
    expires_at: Optional[str] = None
