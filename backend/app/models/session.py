from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"


class InterviewSession(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    user_id: str
    project_title: str
    status: SessionStatus = SessionStatus.ACTIVE
    phase: str = "exploration"  # exploration|deepening|validation
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
