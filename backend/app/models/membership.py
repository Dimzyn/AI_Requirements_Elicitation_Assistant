from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Membership(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    project_id: str
    user_id: str
    role_in_project: str = "stakeholder"
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
