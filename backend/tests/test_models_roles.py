from app.models.user import User
from app.models.session import InterviewSession, SessionStatus


def test_user_role_status_defaults():
    u = User(email="a@x.com", hashed_password="h", real_name="A")
    assert u.role == "stakeholder"
    assert u.status == "active"


def test_session_is_project_scoped():
    s = InterviewSession(project_id="p1", stakeholder_id="u1")
    assert s.project_id == "p1"
    assert s.stakeholder_id == "u1"
    assert s.status == SessionStatus.ACTIVE
