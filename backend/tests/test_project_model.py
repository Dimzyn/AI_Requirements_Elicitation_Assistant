from app.models.project import Project


def test_project_defaults_and_required():
    p = Project(owner_id="re1", title="Hospital System")
    assert p.owner_id == "re1"
    assert p.title == "Hospital System"
    assert p.background is None
    assert p.created_at <= p.updated_at


def test_project_accepts_optional_context():
    p = Project(owner_id="re1", title="X", background="b", goals="g", scope="s")
    assert (p.background, p.goals, p.scope) == ("b", "g", "s")
