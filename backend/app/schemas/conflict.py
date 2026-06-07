from datetime import datetime

from pydantic import BaseModel


class RequirementRef(BaseModel):
    id: str
    statement: str
    stakeholder: str | None = None


class ConflictOut(BaseModel):
    id: str
    project_id: str
    status: str
    explanation: str
    requirement_a: RequirementRef
    requirement_b: RequirementRef
    detected_at: datetime


class ConflictPatch(BaseModel):
    status: str
