from app.models.membership import Membership


def test_membership_defaults():
    m = Membership(project_id="p1", user_id="u1")
    assert m.project_id == "p1"
    assert m.user_id == "u1"
    assert m.role_in_project == "stakeholder"
    assert m.joined_at is not None
