from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class RequirementOut(BaseModel):
    id: str
    session_id: str
    statement: str
    type: str
    source_turn_id: str
    priority: str | None = None
    status: str | None = None
    acceptance_criteria: str | None = None
    edited_by: str | None = None
    edited_at: str | None = None
    created_at: datetime


class RequirementPatch(BaseModel):
    statement: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    acceptance_criteria: Optional[str] = None
