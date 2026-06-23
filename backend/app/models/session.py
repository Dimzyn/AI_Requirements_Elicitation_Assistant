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
    project_id: str
    stakeholder_id: str
    title: Optional[str] = None  # conversation label, auto-named from first message
    kind: str = "interview"  # interview | conflict_resolution
    conflict_id: Optional[str] = None  # set when kind == conflict_resolution
    status: SessionStatus = SessionStatus.ACTIVE
    phase: str = "exploration"  # exploration|deepening|validation
    summary: Optional[str] = None
    # Elicitation-end signals (interview sessions only). saturation_streak counts
    # consecutive stakeholder turns that produced no NEW requirement; once it hits
    # the threshold the agent suggests wrapping up. stakeholder_finished is the
    # stakeholder's "I'm done" — the RE still confirms via complete_session.
    saturation_streak: int = 0
    wrap_up_suggested: bool = False
    stakeholder_finished: bool = False
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
