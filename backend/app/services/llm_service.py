from typing import Any, Optional

from ..config import settings


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
    """

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
        resp = await self._client.generate(
            model=model or self.model,
            contents=prompt,
            config=config,
        )
        return resp.text
