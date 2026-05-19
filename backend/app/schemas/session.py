from pydantic import BaseModel


class SessionCreate(BaseModel):
    project_title: str


class SessionOut(BaseModel):
    id: str
    project_title: str
    status: str
    phase: str
