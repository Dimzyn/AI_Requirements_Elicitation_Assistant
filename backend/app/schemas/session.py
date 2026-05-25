from pydantic import BaseModel


class SessionCreate(BaseModel):
    project_title: str


class SessionOut(BaseModel):
    id: str
    project_title: str
    status: str
    phase: str
    user_id: str | None = None
    created_at: str | None = None
