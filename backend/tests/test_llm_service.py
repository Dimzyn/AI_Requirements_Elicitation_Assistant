import pytest
from app.services.llm_service import LLMService, UpstreamUnavailable


class FakeClient:
    """Matches the minimal surface LLMService.generate uses."""

    def __init__(self):
        self.calls = []

    async def generate(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": dict(config)})
        return type("R", (), {"text": '{"question": "Why?"}'})()


class ServerError(Exception):
    """Mimics google.genai.errors.ServerError by name + payload."""
    def __init__(self, code, message):
        super().__init__(f"{code} UNAVAILABLE. {message}")
        self.code = code


class FlakyClient:
    """Raises N 503s then succeeds. Used to test LLMService retry."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    async def generate(self, *, model, contents, config):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ServerError(503, "high demand")
        return type("R", (), {"text": "ok"})()


class AlwaysDownClient:
    async def generate(self, *, model, contents, config):
        raise ServerError(503, "still down")


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


@pytest.mark.asyncio
async def test_recovers_after_one_transient_503(monkeypatch):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    fc = FlakyClient(fail_times=1)
    svc = LLMService(client=fc, model="m")
    out = await svc.generate("hi", temperature=0.5)
    assert out == "ok"
    assert fc.calls == 2  # 1 failure + 1 success


@pytest.mark.asyncio
async def test_recovers_after_two_transient_503s(monkeypatch):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    fc = FlakyClient(fail_times=2)
    svc = LLMService(client=fc, model="m")
    out = await svc.generate("hi", temperature=0.5)
    assert out == "ok"
    assert fc.calls == 3


@pytest.mark.asyncio
async def test_raises_upstream_unavailable_after_all_retries_fail(monkeypatch):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    svc = LLMService(client=AlwaysDownClient(), model="m")
    with pytest.raises(UpstreamUnavailable):
        await svc.generate("hi", temperature=0.5)


class NonTransientError(Exception):
    pass


class HardFailClient:
    async def generate(self, *, model, contents, config):
        raise NonTransientError("bad prompt")


@pytest.mark.asyncio
async def test_non_transient_errors_are_not_retried():
    svc = LLMService(client=HardFailClient(), model="m")
    with pytest.raises(NonTransientError):
        await svc.generate("hi", temperature=0.5)
