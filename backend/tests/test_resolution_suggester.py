import pytest

from app.services.llm_service import UpstreamUnavailable
from app.services.resolution_suggester import ResolutionSuggester


class Stub:
    def __init__(self, payload='{"suggestion": "Refunds under $50 auto-approve; above need sign-off.", "rationale": "Compromise."}'):
        self.payload = payload
        self.last_kwargs = None

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.last_kwargs = dict(temperature=temperature, response_mime_type=response_mime_type, prompt=prompt)
        return self.payload


@pytest.mark.asyncio
async def test_suggest_embeds_captured_stances_in_prompt():
    stub = Stub()
    out = await ResolutionSuggester(llm=stub).suggest(
        statement_a="Auto-approve all refunds.",
        statement_b="All refunds require manager sign-off.",
        explanation="Cannot both hold.",
        transcript=[{"role": "stakeholder", "content": "Maybe a threshold."}],
        same_stakeholder=True,
        resolutions=[{"decision": "compromise", "statement": "Threshold-based approval."}],
    )
    assert out["suggestion"].startswith("Refunds under $50")
    assert stub.last_kwargs["temperature"] == 0.3
    # the captured stance is surfaced to the model
    assert "Threshold-based approval." in stub.last_kwargs["prompt"]
    assert "compromise" in stub.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_suggest_without_stances_still_works():
    stub = Stub()
    out = await ResolutionSuggester(llm=stub).suggest(
        statement_a="A", statement_b="B", explanation="E",
        transcript=[], same_stakeholder=False,
    )
    assert out["rationale"] == "Compromise."
    assert "(none captured)" in stub.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_suggest_tolerates_extra_content_after_json():
    stub = Stub('{"suggestion": "Threshold-based approval.", "rationale": "Middle ground."}\nCheers!')
    out = await ResolutionSuggester(llm=stub).suggest(
        statement_a="A", statement_b="B", explanation="E",
        transcript=[], same_stakeholder=False,
    )
    assert out == {"suggestion": "Threshold-based approval.", "rationale": "Middle ground."}


@pytest.mark.asyncio
async def test_suggest_unparseable_payload_raises_upstream_unavailable():
    # The suggest endpoint already maps UpstreamUnavailable to a 503 "try again";
    # an unreadable payload must take that path instead of a raw 500.
    with pytest.raises(UpstreamUnavailable):
        await ResolutionSuggester(llm=Stub("not json at all")).suggest(
            statement_a="A", statement_b="B", explanation="E",
            transcript=[], same_stakeholder=False,
        )


@pytest.mark.asyncio
async def test_suggest_non_dict_payload_raises_upstream_unavailable():
    # A JSON list parses fine but isn't the promised object; it must take the
    # same 503 path instead of escaping as an AttributeError-driven 500.
    with pytest.raises(UpstreamUnavailable):
        await ResolutionSuggester(llm=Stub('["a", "b"]')).suggest(
            statement_a="A", statement_b="B", explanation="E",
            transcript=[], same_stakeholder=False,
        )
