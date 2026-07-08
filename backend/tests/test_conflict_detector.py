import pytest
from app.services.conflict_detector import ConflictDetector


class Stub:
    def __init__(self, payload: str):
        self.payload = payload
        self.last_kwargs = None

    async def generate(self, prompt, *, temperature, response_mime_type=None, model=None):
        self.last_kwargs = dict(
            temperature=temperature,
            response_mime_type=response_mime_type,
            prompt=prompt,
        )
        return self.payload


def _reqs():
    return [
        {"id": "aaa", "statement": "Auto-approve all refunds.", "stakeholder": "Alice", "type": "functional"},
        {"id": "bbb", "statement": "All refunds require manager sign-off.", "stakeholder": "Bob", "type": "functional"},
        {"id": "ccc", "statement": "Support dark mode.", "stakeholder": "Bob", "type": "functional"},
    ]


@pytest.mark.asyncio
async def test_detect_maps_indices_to_requirement_ids():
    stub = Stub('{"conflicts": [{"a": 0, "b": 1, "explanation": "Cannot both auto-approve and require sign-off."}]}')
    det = ConflictDetector(llm=stub)
    out = await det.detect(_reqs())
    assert len(out) == 1
    # ids are returned sorted so requirement_a <= requirement_b
    assert out[0]["requirement_a"] == "aaa"
    assert out[0]["requirement_b"] == "bbb"
    assert "sign-off" in out[0]["explanation"]
    assert stub.last_kwargs["temperature"] == 0.2
    assert stub.last_kwargs["response_mime_type"] == "application/json"
    # the prompt must label requirements with their stakeholder
    assert "Alice" in stub.last_kwargs["prompt"]
    assert "Bob" in stub.last_kwargs["prompt"]


@pytest.mark.asyncio
async def test_detect_returns_empty_when_no_conflicts():
    det = ConflictDetector(llm=Stub('{"conflicts": []}'))
    assert await det.detect(_reqs()) == []


@pytest.mark.asyncio
async def test_detect_returns_empty_for_fewer_than_two_requirements():
    det = ConflictDetector(llm=Stub('{"conflicts": [{"a": 0, "b": 0, "explanation": "x"}]}'))
    assert await det.detect([{"id": "only", "statement": "x", "stakeholder": "A", "type": "functional"}]) == []


@pytest.mark.asyncio
async def test_detect_drops_malformed_and_out_of_range_pairs():
    payload = (
        '{"conflicts": ['
        '{"a": 0, "b": 99, "explanation": "out of range"},'      # b out of range
        '{"a": 1, "b": 1, "explanation": "self pair"},'          # a == b
        '{"a": "x", "b": 2, "explanation": "non-int"},'          # non-int index
        '{"explanation": "missing indices"}'                     # missing a/b
        ']}'
    )
    det = ConflictDetector(llm=Stub(payload))
    assert await det.detect(_reqs()) == []


@pytest.mark.asyncio
async def test_detect_returns_empty_on_unparseable_json():
    det = ConflictDetector(llm=Stub("not json at all"))
    assert await det.detect(_reqs()) == []


@pytest.mark.asyncio
async def test_detect_returns_empty_on_non_dict_json():
    # A JSON list parses fine but isn't the promised object; degrade to "none
    # found" instead of escaping as an AttributeError-driven 500.
    det = ConflictDetector(llm=Stub('["not", "an", "object"]'))
    assert await det.detect(_reqs()) == []


@pytest.mark.asyncio
async def test_detect_returns_empty_when_conflicts_is_not_a_list():
    det = ConflictDetector(llm=Stub('{"conflicts": "none that I can see"}'))
    assert await det.detect(_reqs()) == []


@pytest.mark.asyncio
async def test_detect_skips_non_dict_conflict_entries():
    det = ConflictDetector(
        llm=Stub('{"conflicts": ["garbage", {"a": 0, "b": 1, "explanation": "x"}]}')
    )
    out = await det.detect(_reqs())
    assert len(out) == 1
    assert out[0]["requirement_a"] == "aaa"


@pytest.mark.asyncio
async def test_detect_tolerates_extra_content_after_json():
    # gemini-2.5-flash-lite sometimes appends stray text after the JSON document;
    # the detected conflicts must survive instead of degrading to "none found".
    det = ConflictDetector(
        llm=Stub('{"conflicts": [{"a": 0, "b": 1, "explanation": "x"}]}\nExtra notes.')
    )
    out = await det.detect(_reqs())
    assert len(out) == 1
    assert out[0]["requirement_a"] == "aaa"
    assert out[0]["requirement_b"] == "bbb"
