import pytest

from app.services.resolution_tracker import ResolutionTracker


class Stub:
    def __init__(self, payload: str):
        self.payload = payload
        self.last_kwargs = None

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.last_kwargs = dict(temperature=temperature, response_mime_type=response_mime_type, prompt=prompt)
        return self.payload


_TRANSCRIPT = [{"role": "stakeholder", "content": "Let's just auto-approve everything."}]


@pytest.mark.asyncio
async def test_track_returns_reached_decision_and_statement():
    stub = Stub('{"reached": true, "decision": "a_wins", "statement": "Auto-approve all refunds."}')
    out = await ResolutionTracker(llm=stub).track(
        statement_a="Auto-approve all refunds.",
        statement_b="All refunds require manager sign-off.",
        explanation="Cannot both hold.",
        transcript=_TRANSCRIPT,
        same_stakeholder=True,
    )
    assert out == {"reached": True, "decision": "a_wins", "statement": "Auto-approve all refunds."}
    assert stub.last_kwargs["temperature"] == 0.2
    assert stub.last_kwargs["response_mime_type"] == "application/json"
    # both statements are shown to the model
    assert "Auto-approve all refunds." in stub.last_kwargs["prompt"]
    assert "All refunds require manager sign-off." in stub.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_track_not_reached_when_flag_false():
    stub = Stub('{"reached": false, "decision": null, "statement": null}')
    out = await ResolutionTracker(llm=stub).track(
        statement_a="A", statement_b="B", explanation="E", transcript=_TRANSCRIPT, same_stakeholder=False
    )
    assert out == {"reached": False, "decision": None, "statement": None}


@pytest.mark.asyncio
async def test_track_invalid_decision_is_not_reached():
    stub = Stub('{"reached": true, "decision": "banana", "statement": "x"}')
    out = await ResolutionTracker(llm=stub).track(
        statement_a="A", statement_b="B", explanation="E", transcript=_TRANSCRIPT, same_stakeholder=False
    )
    assert out == {"reached": False, "decision": None, "statement": None}


@pytest.mark.asyncio
async def test_track_unparseable_json_is_not_reached():
    out = await ResolutionTracker(llm=Stub("not json at all")).track(
        statement_a="A", statement_b="B", explanation="E", transcript=_TRANSCRIPT, same_stakeholder=False
    )
    assert out == {"reached": False, "decision": None, "statement": None}


@pytest.mark.asyncio
async def test_track_tolerates_extra_content_after_json():
    # A reached resolution must not be silently downgraded to "keep probing"
    # just because the model appended stray text after the JSON document.
    stub = Stub('{"reached": true, "decision": "b_wins", "statement": "Sign-off required."}\nDone!')
    out = await ResolutionTracker(llm=stub).track(
        statement_a="A", statement_b="B", explanation="E", transcript=_TRANSCRIPT, same_stakeholder=False
    )
    assert out == {"reached": True, "decision": "b_wins", "statement": "Sign-off required."}
