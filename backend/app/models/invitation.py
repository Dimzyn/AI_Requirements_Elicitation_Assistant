from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


def _default_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=7)


class Invitation(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    email: EmailStr
    token: str
    status: InvitationStatus = InvitationStatus.PENDING
    expires_at: datetime = Field(default_factory=_default_expiry)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
