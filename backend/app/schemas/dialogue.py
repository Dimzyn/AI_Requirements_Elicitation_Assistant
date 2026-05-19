from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional


class TurnIn(BaseModel):
    content: str = Field(min_length=1)


class QuestionOut(BaseModel):
    id: str
    content: str
    strategy: str


class TurnResponse(BaseModel):
    stakeholder_turn_id: str
    questions: List[QuestionOut]


class TurnOut(BaseModel):
    id: str
    role: str
    content: str
    strategy: Optional[str] = None
    created_at: datetime
