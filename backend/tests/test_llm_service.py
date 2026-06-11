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


class ClientError(Exception):
    """Mimics google.genai.errors.ClientError (e.g. 429) by name + payload."""
    def __init__(self, code, message):
        super().__init__(f"{code} {message}")
        self.code = code


class ModelAwareClient:
    """Raises a transient error for models in ``down`` and succeeds otherwise."""

    def __init__(self, down: set[str], exc):
        self.down = down
        self.exc = exc
        self.models_tried: list[str] = []

    async def generate(self, *, model, contents, config):
        self.models_tried.append(model)
        if model in self.down:
            raise self.exc
        return type("R", (), {"text": f"ok:{model}"})()


@pytest.mark.asyncio
async def test_falls_back_to_secondary_model_when_primary_overloaded(monkeypatch):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    client = ModelAwareClient(down={"primary-m"}, exc=ServerError(503, "high demand"))
    svc = LLMService(client=client, model="primary-m", fallback_model="fallback-m")
    out = await svc.generate("hi", temperature=0.5)
    assert out == "ok:fallback-m"
    assert "fallback-m" in client.models_tried


@pytest.mark.asyncio
async def test_raises_upstream_unavailable_when_both_models_overloaded(monkeypatch):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    client = ModelAwareClient(
        down={"primary-m", "fallback-m"}, exc=ServerError(503, "down")
    )
    svc = LLMService(client=client, model="primary-m", fallback_model="fallback-m")
    with pytest.raises(UpstreamUnavailable):
        await svc.generate("hi", temperature=0.5)


@pytest.mark.asyncio
async def test_retries_on_429_resource_exhausted(monkeypatch):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    client = ModelAwareClient(
        down={"primary-m"},
        exc=ClientError(429, "RESOURCE_EXHAUSTED"),
    )
    svc = LLMService(client=client, model="primary-m", fallback_model="fallback-m")
    out = await svc.generate("hi", temperature=0.5)
    assert out == "ok:fallback-m"


class PerModelClient:
    """Maps each model name to an exception instance (raise) or None (succeed)."""

    def __init__(self, behavior: dict):
        self.behavior = behavior
        self.models_tried: list[str] = []

    async def generate(self, *, model, contents, config):
        self.models_tried.append(model)
        exc = self.behavior.get(model)
        if exc is not None:
            raise exc
        return type("R", (), {"text": f"ok:{model}"})()


@pytest.mark.asyncio
async def test_fallback_non_transient_error_degrades_to_upstream_unavailable(monkeypatch):
    # Primary overloaded (503), fallback model raises a non-transient 404 (e.g.
    # a retired model). The request must degrade to UpstreamUnavailable (-> 503),
    # never let the raw 404 escape as a 500.
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    client = PerModelClient(
        {
            "primary-m": ServerError(503, "high demand"),
            "fallback-m": ClientError(404, "NOT_FOUND model retired"),
        }
    )
    svc = LLMService(client=client, model="primary-m", fallback_model="fallback-m")
    with pytest.raises(UpstreamUnavailable):
        await svc.generate("hi", temperature=0.5)
    assert "fallback-m" in client.models_tried


@pytest.mark.asyncio
async def test_primary_non_transient_error_still_propagates_without_fallback(monkeypatch):
    # A non-transient error on the PRIMARY is a real bug and must surface raw,
    # without silently masking it behind the fallback.
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    client = PerModelClient(
        {
            "primary-m": ClientError(400, "INVALID_ARGUMENT bad prompt"),
            "fallback-m": None,
        }
    )
    svc = LLMService(client=client, model="primary-m", fallback_model="fallback-m")
    with pytest.raises(ClientError):
        await svc.generate("hi", temperature=0.5)
    assert client.models_tried == ["primary-m"]  # fallback never attempted


@pytest.mark.asyncio
async def test_fallback_engagement_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    client = ModelAwareClient(down={"primary-m"}, exc=ServerError(503, "high demand"))
    svc = LLMService(client=client, model="primary-m", fallback_model="fallback-m")
    with caplog.at_level("WARNING", logger="app.services.llm_service"):
        await svc.generate("hi", temperature=0.5)
    fallback_logs = [
        r for r in caplog.records if "falling back" in r.getMessage().lower()
    ]
    assert len(fallback_logs) == 1
    msg = fallback_logs[0].getMessage()
    assert "primary-m" in msg and "fallback-m" in msg


@pytest.mark.asyncio
async def test_no_fallback_log_when_primary_succeeds(monkeypatch, caplog):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    fc = FakeClient()
    svc = LLMService(client=fc, model="primary-m", fallback_model="fallback-m")
    with caplog.at_level("WARNING", logger="app.services.llm_service"):
        await svc.generate("hi", temperature=0.5)
    assert not [r for r in caplog.records if "falling back" in r.getMessage().lower()]


@pytest.mark.asyncio
async def test_retries_on_500_internal(monkeypatch):
    monkeypatch.setattr(LLMService, "RETRY_DELAYS", (0, 0, 0))
    client = ModelAwareClient(
        down={"primary-m"},
        exc=ServerError(500, "INTERNAL"),
    )
    svc = LLMService(client=client, model="primary-m", fallback_model="fallback-m")
    out = await svc.generate("hi", temperature=0.5)
    assert out == "ok:fallback-m"
