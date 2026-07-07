import pytest
from app.services.llm_service import UpstreamUnavailable
from app.services.question_generator import (
    QuestionGenerator,
    GeneratedQuestion,
    QuestionParseError,
)


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


CONFLICT_HISTORY_START = [
    {"role": "agent", "content": "Here are two clashing requirements — how should we resolve them?"},
    {"role": "stakeholder", "content": "Well, both are important to me for different reasons."},
]


@pytest.mark.asyncio
async def test_conflict_kind_first_probe_clarifies_first_requirement():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(
        phase="validation", summary="conflict ctx", history=CONFLICT_HISTORY_START, kind="conflict_resolution"
    )
    assert result.strategy == "clarify_intent_a"
    # the conflict directive (not an interview one) is embedded in the single prompt
    assert "FIRST conflicting requirement" in llm.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_conflict_kind_progression_advances_with_prior_conflict_turns():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    history = CONFLICT_HISTORY_START + [
        {"role": "agent", "content": "Q1?", "strategy": "clarify_intent_a"},
        {"role": "stakeholder", "content": "Because it saves the team a lot of manual effort."},
    ]
    result = await g.next_question(
        phase="validation", summary="conflict ctx", history=history, kind="conflict_resolution"
    )
    assert result.strategy == "clarify_intent_b"


@pytest.mark.asyncio
async def test_interview_kind_unchanged_default():
    llm = RecordingLLM()
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert result.strategy == "concept"  # default kind stays interview


class SequenceLLM:
    """Returns scripted payloads in order, repeating the last one when exhausted."""

    def __init__(self, *payloads):
        self.payloads = list(payloads)
        self.calls = 0

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return payload


@pytest.mark.asyncio
async def test_unparseable_payload_raises_parse_error_after_one_retry():
    # Gemini can return non-JSON despite response_mime_type="application/json";
    # that must surface as QuestionParseError, never a raw JSONDecodeError.
    llm = SequenceLLM("definitely not json")
    g = QuestionGenerator(llm=llm)
    with pytest.raises(QuestionParseError):
        await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert llm.calls == 2  # the parse failure is retried exactly once


@pytest.mark.asyncio
async def test_parse_error_is_an_upstream_unavailable():
    # Routers map UpstreamUnavailable to 503, so the parse error must be one.
    llm = SequenceLLM("garbage")
    g = QuestionGenerator(llm=llm)
    with pytest.raises(UpstreamUnavailable):
        await g.next_question(phase="exploration", summary="", history=HISTORY)


@pytest.mark.asyncio
async def test_non_dict_json_payload_raises_parse_error():
    # A JSON list parses fine but has no .get(); it must not escape as AttributeError.
    llm = SequenceLLM('["draft_question", "why?"]')
    g = QuestionGenerator(llm=llm)
    with pytest.raises(QuestionParseError):
        await g.next_question(phase="exploration", summary="", history=HISTORY)


@pytest.mark.asyncio
async def test_none_payload_raises_parse_error():
    # The SDK yields resp.text=None when a response carries no text part.
    llm = SequenceLLM(None)
    g = QuestionGenerator(llm=llm)
    with pytest.raises(QuestionParseError):
        await g.next_question(phase="exploration", summary="", history=HISTORY)


@pytest.mark.asyncio
async def test_recovers_when_retry_returns_parseable_payload():
    llm = SequenceLLM("oops", '{"draft_question": "What is the refund window?"}')
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert result.question == "What is the refund window?"
    assert result.attempts == 2
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_non_dict_payload_is_retried_then_succeeds():
    llm = SequenceLLM(
        '["draft_question", "not an object"]',
        '{"draft_question": "What does closing time look like?"}',
    )
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert result.question == "What does closing time look like?"
    assert llm.calls == 2


@pytest.mark.asyncio
async def test_extra_content_after_json_is_tolerated():
    # gemini-2.5-flash-lite occasionally appends stray content after the JSON
    # document even in JSON mode (live failure 2026-07-07: "Extra data" errors).
    # Lenient parsing must rescue it without burning a regeneration.
    llm = SequenceLLM(
        '{"draft_question": "How do you currently handle refunds?"}\n\nHope this helps!'
    )
    g = QuestionGenerator(llm=llm)
    result = await g.next_question(phase="exploration", summary="", history=HISTORY)
    assert "refunds" in result.question
    assert llm.calls == 1
    assert result.attempts == 1
