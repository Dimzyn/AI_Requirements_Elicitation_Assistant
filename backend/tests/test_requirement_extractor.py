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


@pytest.mark.asyncio
async def test_extract_tolerates_extra_content_after_json():
    # Requirements from a turn must not be dropped just because the model
    # appended stray text after the JSON document ("Extra data" errors).
    stub = Stub(
        '{"requirements": [{"statement":"Users can pay by card.","type":"functional"}]}'
        "\n\nLet me know if you need anything else."
    )
    out = await RequirementExtractor(llm=stub).extract("I want a payment app.")
    assert out == [{"statement": "Users can pay by card.", "type": "functional"}]


@pytest.mark.asyncio
async def test_extract_caps_at_five():
    # A long reply can yield several requirements; we keep at most 5 (raised from 3
    # so a measurable NFR isn't truncated away behind earlier functional ones).
    items = ", ".join(f'{{"statement":"Req {i}.","type":"functional"}}' for i in range(8))
    ex = RequirementExtractor(llm=Stub(f'{{"requirements": [{items}]}}'))
    out = await ex.extract("a reply mentioning many things")
    assert len(out) == 5
