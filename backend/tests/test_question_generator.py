import pytest
from app.services.question_generator import QuestionGenerator, GeneratedQuestion


class ScriptedLLM:
    """Returns a fixed sequence of strings, one per generate() call."""
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.calls.append({
            "prompt": prompt,
            "temperature": temperature,
            "response_mime_type": response_mime_type,
            "model": model,
        })
        return self.outputs.pop(0)


@pytest.mark.asyncio
async def test_first_draft_passes():
    llm = ScriptedLLM([
        '{"draft_question": "How do you currently handle refunds?"}',
        '{"valid": true, "mistakes": [], "correction": ""}',
    ])
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(
        phase="exploration",
        summary="",
        history=[{"role": "stakeholder", "content": "I want a payment app for online retail."}],
    )
    assert isinstance(result, GeneratedQuestion)
    assert "refunds" in result.question
    assert result.attempts == 1
    assert result.valid is True
    assert result.mistakes == []
    assert result.strategy == "concept"  # first agent turn defaults to concept


@pytest.mark.asyncio
async def test_first_draft_uses_high_temperature():
    llm = ScriptedLLM([
        '{"draft_question": "Q1?"}',
        '{"valid": true, "mistakes": [], "correction": ""}',
    ])
    g = QuestionGenerator(llm=llm)
    await g.next_question(phase="exploration", summary="", history=[
        {"role": "stakeholder", "content": "I want a payment app for online retail."}
    ])
    # first call = draft (temp 0.7); second call = validator (temp 0.1)
    assert llm.calls[0]["temperature"] == 0.7
    assert llm.calls[1]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_retries_on_leading_question():
    llm = ScriptedLLM([
        '{"draft_question": "Don\'t you think we should use Stripe?"}',
        '{"valid": false, "mistakes": ["leading"], "correction": "Ask which payment providers they are considering."}',
        '{"draft_question": "Which payment providers are you considering?"}',
        '{"valid": true, "mistakes": [], "correction": ""}',
    ])
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=[
        {"role": "stakeholder", "content": "I want a payment app for online retail."}
    ])
    assert "providers" in result.question
    assert result.attempts == 2
    assert result.valid is True


@pytest.mark.asyncio
async def test_retry_uses_low_temperature():
    llm = ScriptedLLM([
        '{"draft_question": "Bad?"}',
        '{"valid": false, "mistakes": ["vague"], "correction": "Be specific."}',
        '{"draft_question": "Better?"}',
        '{"valid": true, "mistakes": [], "correction": ""}',
    ])
    g = QuestionGenerator(llm=llm)
    await g.next_question(phase="exploration", summary="", history=[
        {"role": "stakeholder", "content": "I want a payment app for online retail."}
    ])
    # calls: [0] draft 0.7, [1] validator 0.1, [2] retry-draft 0.1, [3] validator 0.1
    assert llm.calls[0]["temperature"] == 0.7
    assert llm.calls[2]["temperature"] == 0.1


@pytest.mark.asyncio
async def test_gives_up_after_max_retries():
    # always bad: 3 drafts + 3 validations = 6 calls
    llm = ScriptedLLM([
        '{"draft_question": "Bad1?"}',
        '{"valid": false, "mistakes": ["leading"], "correction": "fix"}',
        '{"draft_question": "Bad2?"}',
        '{"valid": false, "mistakes": ["leading"], "correction": "fix"}',
        '{"draft_question": "Bad3?"}',
        '{"valid": false, "mistakes": ["leading"], "correction": "fix"}',
    ])
    g = QuestionGenerator(llm=llm, max_retries=3)
    result = await g.next_question(phase="exploration", summary="", history=[
        {"role": "stakeholder", "content": "I want a payment app for online retail."}
    ])
    assert result.attempts == 3
    assert result.valid is False
    assert "leading" in result.mistakes
    assert result.question == "Bad3?"
