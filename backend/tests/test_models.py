import pytest
from datetime import datetime
from app.models.user import User
from app.models.session import InterviewSession, SessionStatus
from app.models.turn import DialogueTurn, TurnRole
from app.models.requirement import Requirement, RequirementType

def test_user_requires_email():
    with pytest.raises(ValueError):
        User(email="", hashed_password="x", real_name="A")

def test_session_default_active():
    s = InterviewSession(user_id="u1", project_title="P")
    assert s.status == SessionStatus.ACTIVE

def test_turn_role_enum():
    t = DialogueTurn(session_id="s1", role=TurnRole.STAKEHOLDER, content="hi")
    assert t.role == TurnRole.STAKEHOLDER

def test_requirement_type_enum():
    r = Requirement(session_id="s1", statement="must do X", type=RequirementType.FUNCTIONAL)
    assert r.type == RequirementType.FUNCTIONAL
