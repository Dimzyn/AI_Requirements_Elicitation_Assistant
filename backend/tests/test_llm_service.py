import pytest
from app.services.llm_service import LLMService


class FakeClient:
    """Matches the minimal surface LLMService.generate uses."""

    def __init__(self):
        self.calls = []

    async def generate(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": dict(config)})
        return type("R", (), {"text": '{"question": "Why?"}'})()


@pytest.mark.asyncio
async def test_generate_passes_temperature_and_returns_text():
    fc = FakeClient()
    svc = LLMService(client=fc, model="gemini-2.5-flash")
    out = await svc.generate("hi", temperature=0.7)
    assert out == '{"question": "Why?"}'
    assert fc.calls[0]["config"]["temperature"] == 0.7
    assert fc.calls[0]["model"] == "gemini-2.5-flash"


@pytest.mark.asyncio
async def test_response_mime_type_threaded_through():
    fc = FakeClient()
    svc = LLMService(client=fc, model="m")
    await svc.generate("x", temperature=0.1, response_mime_type="application/json")
    cfg = fc.calls[0]["config"]
    assert cfg["temperature"] == 0.1
    assert cfg["response_mime_type"] == "application/json"


@pytest.mark.asyncio
async def test_model_override_per_call():
    fc = FakeClient()
    svc = LLMService(client=fc, model="default-m")
    await svc.generate("x", temperature=0.5, model="override-m")
    assert fc.calls[0]["model"] == "override-m"
