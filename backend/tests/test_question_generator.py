import pytest
from app.services.question_generator import QuestionGenerator, GeneratedQuestion


class RecordingLLM:
    """Records each generate() call and returns a scripted JSON payload."""

    def __init__(self, payload='{"draft_question": "How do you currently handle refunds?"}'):
        self.payload = payload
        self.calls = []

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.calls.append({
            "prompt": prompt,
            "temperature": temperature,
            "response_mime_type": response_mime_type,
            "model": model,
        })
        return self.payload


HISTORY = [{"role": "stakeholder", "content": "I want a payment app for online retail."}]


@pytest.mark.asyncio
async def test_single_call_returns_question():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert isinstance(result, GeneratedQuestion)
    assert "refunds" in result.question
    assert result.attempts == 1
    assert result.valid is True
    assert result.mistakes == []
    assert result.strategy == "concept"  # first agent turn defaults to concept


@pytest.mark.asyncio
async def test_generates_in_a_single_high_temperature_call():
    # Option A folds validation into generation: exactly ONE LLM round-trip.
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert len(llm.calls) == 1
    assert llm.calls[0]["temperature"] == 0.7
    assert llm.calls[0]["response_mime_type"] == "application/json"


@pytest.mark.asyncio
async def test_prompt_embeds_strategy_and_mistake_taxonomy():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    await g.next_question(phase="exploration", summary="", history=HISTORY)
    prompt = llm.calls[0]["prompt"]
    # the single prompt carries the strategy directive ...
    assert "Strategy directive:" in prompt
    # ... and the 14-mistake taxonomy as an inline generation guard.
    assert "MUST NOT commit" in prompt
    for mistake_id in ("leading", "compound", "vague", "missing_nonfunctional"):
        assert mistake_id in prompt


@pytest.mark.asyncio
async def test_short_reply_selects_general_strategy():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    history = [
        {"role": "stakeholder", "content": "I want a payment app for online retail."},
        {"role": "agent", "content": "Q1?", "strategy": "concept"},
        {"role": "stakeholder", "content": "Yes."},  # short reply -> general
    ]
    result = await g.next_question(phase="exploration", summary="", history=history)
    assert result.strategy == "general"


@pytest.mark.asyncio
async def test_missing_draft_question_yields_empty_string():
    # A malformed payload without draft_question degrades to an empty question
    # rather than raising, so a single bad turn can't 500 the dialogue endpoint.
    llm = RecordingLLM(payload='{"sub_steps": [], "knowledge_gap": "x"}')
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert result.question == ""
    assert result.valid is True
