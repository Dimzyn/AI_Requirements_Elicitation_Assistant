from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class User(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    email: EmailStr
    hashed_password: str
    real_name: str
    phone: Optional[str] = None
    domain_level: str = "novice"  # novice|intermediate|expert
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("email")
    @classmethod
    def _non_empty(cls, v):
        if not v:
            raise ValueError("email required")
        return v
