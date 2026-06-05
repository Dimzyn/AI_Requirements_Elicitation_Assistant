import asyncio
import logging
from typing import Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class UpstreamUnavailable(RuntimeError):
    """Raised when the LLM upstream returns 503 after all retries exhausted."""


def _is_transient_503(exc: BaseException) -> bool:
    """Duck-type detection of Gemini 503/UNAVAILABLE without importing google.genai."""
    if type(exc).__name__ == "ServerError":
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code == 503:
            return True
    msg = str(exc)
    return "503" in msg and ("UNAVAILABLE" in msg or "unavailable" in msg)


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

    Transient 503 UNAVAILABLE responses from Gemini are retried with exponential
    backoff before being converted to UpstreamUnavailable.
    """

    MAX_RETRIES = 3
    RETRY_DELAYS = (1.0, 2.0, 4.0)

    def __init__(self, *, client: Any | None = None, model: str | None = None):
        if client is None:
            from google import genai

            sdk = genai.Client(api_key=settings.gemini_api_key)
            client = _GeminiClientAdapter(sdk)
        self._client = client
        self.model = model or settings.gemini_model

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

        last_exc: BaseException | None = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = await self._client.generate(
                    model=model or self.model,
                    contents=prompt,
                    config=config,
                )
                return resp.text
            except Exception as exc:
                if not _is_transient_503(exc):
                    raise
                last_exc = exc
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_DELAYS[min(attempt, len(self.RETRY_DELAYS) - 1)]
                    logger.warning(
                        "Gemini 503 UNAVAILABLE on attempt %d/%d, retrying in %.1fs",
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
        raise UpstreamUnavailable(
            "Gemini is temporarily overloaded. Try again in a moment."
        ) from last_exc
