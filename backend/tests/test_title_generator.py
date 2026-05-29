import pytest
from app.services.title_generator import TitleGenerator, DEFAULT_TITLE


class Stub:
    def __init__(self, payload: str):
        self.payload = payload
        self.last = None

    async def generate(self, prompt, *, temperature=0.7, response_mime_type=None, model=None):
        self.last = dict(temperature=temperature, prompt_snippet=prompt[:60])
        return self.payload


@pytest.mark.asyncio
async def test_generate_strips_quotes_and_trailing_period():
    stub = Stub('"Calendar Task Sync".')
    g = TitleGenerator(llm=stub)
    out = await g.generate("sync my todos with google calendar")
    assert out == "Calendar Task Sync"
    assert stub.last["temperature"] == 0.3


@pytest.mark.asyncio
async def test_generate_collapses_whitespace_and_caps_word_count():
    g = TitleGenerator(llm=Stub("one  two\nthree four five six seven eight"))
    assert await g.generate("x") == "one two three four five six"


@pytest.mark.asyncio
async def test_generate_falls_back_to_placeholder_on_empty():
    g = TitleGenerator(llm=Stub("   \n  "))
    assert await g.generate("x") == DEFAULT_TITLE
