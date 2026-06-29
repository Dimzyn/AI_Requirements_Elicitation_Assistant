from datetime import datetime

from pydantic import BaseModel


class RequirementRef(BaseModel):
    id: str
    statement: str
    stakeholder: str | None = None


class ResolutionSessionRef(BaseModel):
    id: str
    stakeholder: str | None = None


class ProposalOut(BaseModel):
    statement: str
    rationale: str | None = None
    published_at: datetime


class VoteOut(BaseModel):
    stakeholder: str | None = None
    choice: str
    comment: str | None = None
    voted_at: datetime


class ProposeIn(BaseModel):
    statement: str
    rationale: str | None = None


class ConflictOut(BaseModel):
    id: str
    project_id: str
    status: str
    explanation: str
    requirement_a: RequirementRef
    requirement_b: RequirementRef
    resolution_sessions: list[ResolutionSessionRef] = []
    proposal: ProposalOut | None = None
    votes: list[VoteOut] = []
    detected_at: datetime


class ConflictPatch(BaseModel):
    status: str


class ResolutionSuggestion(BaseModel):
    suggestion: str
    rationale: str


class ApplyIn(BaseModel):
    surviving_requirement_id: str
    statement: str


class ApplyOut(BaseModel):
    id: str
    status: str


class VoteIn(BaseModel):
    choice: str
    comment: str | None = None


class ResolutionCardOut(BaseModel):
    proposal: ProposalOut | None = None
    my_vote: VoteOut | None = None
