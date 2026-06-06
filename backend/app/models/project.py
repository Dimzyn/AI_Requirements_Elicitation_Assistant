from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Project(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    owner_id: str
    title: str
    background: Optional[str] = None
    goals: Optional[str] = None
    scope: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
