import pytest
from app.services.mistake_validator import MistakeValidator, Verdict


class StubLLM:
    def __init__(self, payload: str):
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


@pytest.mark.asyncio
async def test_validator_accepts_clean_question():
    llm = StubLLM('{"valid": true, "mistakes": [], "correction": ""}')
    v = MistakeValidator(llm=llm)
    verdict = await v.validate("How do you currently handle refunds?")
    assert isinstance(verdict, Verdict)
    assert verdict.valid is True
    assert verdict.mistakes == []
    assert verdict.correction == ""


@pytest.mark.asyncio
async def test_validator_flags_leading_question():
    llm = StubLLM('{"valid": false, "mistakes": ["leading"], "correction": "Rephrase neutrally."}')
    v = MistakeValidator(llm=llm)
    verdict = await v.validate("Don't you think we should use Stripe?")
    assert verdict.valid is False
    assert "leading" in verdict.mistakes
    assert verdict.correction == "Rephrase neutrally."


@pytest.mark.asyncio
async def test_validator_uses_low_temperature_and_json_mime():
    llm = StubLLM('{"valid": true, "mistakes": [], "correction": ""}')
    v = MistakeValidator(llm=llm)
    await v.validate("Q?")
    assert llm.calls[0]["temperature"] == 0.1
    assert llm.calls[0]["response_mime_type"] == "application/json"


@pytest.mark.asyncio
async def test_validator_includes_taxonomy_in_prompt():
    llm = StubLLM('{"valid": true, "mistakes": [], "correction": ""}')
    v = MistakeValidator(llm=llm)
    await v.validate("Q?")
    prompt = llm.calls[0]["prompt"]
    # The 14 taxonomy ids should all appear in the prompt:
    for mid in ["leading", "compound", "vague", "yes_no", "assumption",
                "jargon", "off_topic", "duplicate", "solution_oriented",
                "double_barrelled", "negative", "speculative",
                "missing_nonfunctional", "missing_edge_case"]:
        assert mid in prompt
