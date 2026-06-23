from typing import Optional

from pydantic import BaseModel


class SessionOut(BaseModel):
    id: str
    project_id: str
    stakeholder_id: str
    title: Optional[str] = None
    kind: str = "interview"
    conflict_id: Optional[str] = None
    status: str
    phase: str
    stakeholder_finished: bool = False
    created_at: Optional[str] = None
    stakeholder_name: Optional[str] = None
    stakeholder_email: Optional[str] = None
