import pytest
from app.services.requirement_extractor import RequirementExtractor


class Stub:
    def __init__(self, payload: str):
        self.payload = payload
        self.last_kwargs = None

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.last_kwargs = dict(
            temperature=temperature,
            response_mime_type=response_mime_type,
            prompt_snippet=prompt[:60],
        )
        return self.payload


@pytest.mark.asyncio
async def test_extract_returns_typed_requirements():
    stub = Stub('{"requirements": [{"statement":"Users can pay by card.","type":"functional"}]}')
    ex = RequirementExtractor(llm=stub)
    out = await ex.extract("I want a payment app accepting cards.")
    assert out[0]["statement"].startswith("Users can pay")
    assert out[0]["type"] == "functional"
    assert stub.last_kwargs["temperature"] == 0.2
    assert stub.last_kwargs["response_mime_type"] == "application/json"


@pytest.mark.asyncio
async def test_extract_returns_empty_list_when_no_requirements_field():
    ex = RequirementExtractor(llm=Stub('{"other": []}'))
    assert await ex.extract("garbage in") == []


@pytest.mark.asyncio
async def test_extract_returns_empty_list_when_array_is_empty():
    ex = RequirementExtractor(llm=Stub('{"requirements": []}'))
    assert await ex.extract("vague input") == []
