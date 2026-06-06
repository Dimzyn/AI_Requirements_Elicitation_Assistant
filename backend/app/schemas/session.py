from typing import Optional

from pydantic import BaseModel


class SessionOut(BaseModel):
    id: str
    project_id: str
    stakeholder_id: str
    title: Optional[str] = None
    status: str
    phase: str
    created_at: Optional[str] = None
