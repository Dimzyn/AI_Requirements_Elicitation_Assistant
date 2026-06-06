from typing import Optional

from pydantic import BaseModel, Field


class InvitationView(BaseModel):
    email: str
    project_title: str
    status: str


class AcceptRequest(BaseModel):
    password: str = Field(min_length=8)
    real_name: Optional[str] = None


class AcceptResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
