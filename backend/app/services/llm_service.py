import asyncio
import json
import logging
import random
from typing import Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)

# Gemini status codes worth retrying: the model is transiently overloaded
# (503 UNAVAILABLE), rate-limited (429 RESOURCE_EXHAUSTED), or hit an internal
# blip (500 INTERNAL). All are server-side and usually clear on retry/fallback.
_TRANSIENT_CODES = (429, 500, 503)
_TRANSIENT_MARKERS = ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL")


class UpstreamUnavailable(RuntimeError):
    """Raised when the LLM upstream stays unavailable after retries and fallback."""


def first_json_object(raw: str) -> Any:
    """Parse the first JSON document in a Gemini JSON-mode payload.

    gemini-2.5-flash-lite occasionally appends stray content after the JSON
    document even with response_mime_type="application/json", which strict
    json.loads rejects with "Extra data". Decode the first document and drop
    the trailer; any other malformed payload raises exactly like json.loads.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        if exc.msg != "Extra data":
            raise
        obj, _ = json.JSONDecoder().raw_decode(raw, len(raw) - len(raw.lstrip()))
        return obj


def _is_transient(exc: BaseException) -> bool:
    """Duck-type detection of retryable Gemini errors without importing google.genai."""
    if type(exc).__name__ in ("ServerError", "ClientError"):
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code in _TRANSIENT_CODES:
            return True
    msg = str(exc)
    if any(str(code) in msg for code in _TRANSIENT_CODES) and any(
        marker in msg.upper() for marker in _TRANSIENT_MARKERS
    ):
        return True
    return False


class _GeminiClientAdapter:
    """Adapt google-genai's client.aio.models.generate_content to our internal interface."""

    def __init__(self, sdk_client: Any) -> None:
        self._sdk = sdk_client

    async def generate(self, *, model: str, contents: str, config: dict) -> Any:
        return await self._sdk.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config,
        )


class LLMService:
    """Thin async wrapper over a Gemini-shaped client.

    Tests inject a FakeClient that exposes ``async generate(model=, contents=, config=)``.
    Production uses the real google-genai SDK via _GeminiClientAdapter.

    Transient errors (503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED, 500 INTERNAL) are
    retried with jittered exponential backoff. If the primary model stays
    unavailable, the request falls back to a secondary model (which draws on a
    separate capacity pool) before being converted to UpstreamUnavailable.
    """

    MAX_RETRIES = 3
    RETRY_DELAYS = (1.0, 2.0, 4.0)

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
    ):
        if client is None:
            from google import genai

            sdk = genai.Client(api_key=settings.gemini_api_key)
            client = _GeminiClientAdapter(sdk)
        self._client = client
        self.model = model or settings.gemini_model
        self.fallback_model = fallback_model or settings.gemini_fallback_model

    async def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        response_mime_type: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        config: dict[str, Any] = {"temperature": temperature}
        if response_mime_type:
            config["response_mime_type"] = response_mime_type

        primary = model or self.model
        # Try the primary model, then the fallback (if distinct) on persistent
        # transient failure. Overload is per-model, so a different model often
        # succeeds where retrying the same one does not.
        models = [primary]
        if self.fallback_model and self.fallback_model != primary:
            models.append(self.fallback_model)

        last_exc: BaseException | None = None
        for model_name in models:
            is_fallback = model_name != primary
            if is_fallback:
                # Single greppable line so fallback frequency can be counted
                # (e.g. count("Gemini falling back")) from logs/metrics.
                logger.warning(
                    "Gemini falling back from %s to %s after exhausted retries",
                    primary,
                    model_name,
                )
            try:
                result = await self._generate_with_retry(model_name, prompt, config)
                if is_fallback:
                    logger.info("Gemini fallback model %s succeeded", model_name)
                return result
            except _TransientExhausted as exc:
                last_exc = exc.__cause__
                logger.warning("Gemini model %s exhausted retries", model_name)
            except Exception as exc:
                # A non-transient error on the PRIMARY (e.g. a malformed request)
                # is a real bug and must surface. But the fallback is a best-effort
                # safety net: if it fails for any reason (e.g. a retired model 404),
                # degrade to UpstreamUnavailable rather than crash with a 500.
                if not is_fallback:
                    raise
                last_exc = exc
                logger.error(
                    "Gemini fallback model %s failed (%s); degrading to unavailable",
                    model_name,
                    exc,
                )
        raise UpstreamUnavailable(
            "Gemini is temporarily overloaded. Try again in a moment."
        ) from last_exc

    async def _generate_with_retry(
        self, model_name: str, prompt: str, config: dict[str, Any]
    ) -> str:
        last_exc: BaseException | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = await self._client.generate(
                    model=model_name,
                    contents=prompt,
                    config=config,
                )
                return resp.text
            except Exception as exc:
                if not _is_transient(exc):
                    raise
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    base = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    # Jitter spreads retries to avoid a synchronized thundering herd.
                    delay = base + random.uniform(0, base * 0.25)
                    logger.warning(
                        "Gemini transient error on %s attempt %d/%d, retrying in %.2fs: %s",
                        model_name,
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
        raise _TransientExhausted from last_exc


class _TransientExhausted(RuntimeError):
    """Internal signal: a single model exhausted its retry budget on transient errors."""
