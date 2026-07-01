from datetime import datetime, timezone

from app.schemas.conflict import ConflictOut, RequirementRef, ResolutionCardOut, ResolutionStanceOut
from app.schemas.dialogue import MessageResponse, TurnResponse


def _stance():
    return ResolutionStanceOut(
        stakeholder="Alice", decision="a_wins", statement="Auto-approve refunds.", captured_at=datetime.now(timezone.utc)
    )


def test_resolution_stance_out_shape():
    s = _stance()
    assert s.decision == "a_wins"
    assert s.statement == "Auto-approve refunds."


def test_conflict_out_defaults_resolutions_empty():
    c = ConflictOut(
        id="1", project_id="p", status="open", explanation="e",
        requirement_a=RequirementRef(id="a", statement="A"),
        requirement_b=RequirementRef(id="b", statement="B"),
        detected_at=datetime.now(timezone.utc),
    )
    assert c.resolutions == []


def test_resolution_card_and_responses_optional_resolution():
    assert ResolutionCardOut().my_resolution is None
    assert MessageResponse(stakeholder_turn_id="t").resolution is None
    assert TurnResponse(stakeholder_turn_id="t", questions=[]).resolution is None
