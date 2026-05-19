from datetime import datetime
from pydantic import BaseModel


class RequirementOut(BaseModel):
    id: str
    statement: str
    type: str
    source_turn_id: str
    created_at: datetime
