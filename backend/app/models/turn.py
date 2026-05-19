from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class TurnRole(str, Enum):
    STAKEHOLDER = "stakeholder"
    AGENT = "agent"


class DialogueTurn(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    session_id: str
    role: TurnRole
    content: str
    strategy: Optional[str] = None
    validator_attempts: int = 0
    validator_verdict: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
