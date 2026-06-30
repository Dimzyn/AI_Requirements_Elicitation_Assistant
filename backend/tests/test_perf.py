"""Non-functional perf gate: pin the <5s NFR for QuestionGenerator.next_question.

Per FYP report Chapter 3, the system must produce a probing question in under 5
seconds. This test stubs the LLM so we measure only orchestration overhead
(context build, strategy choice, JSON parsing, dataclass plumbing) on a worst-
case 1000-word stakeholder transcript.
"""

import json
import time

import pytest

from app.services.question_generator import QuestionGenerator


class StubLLM:
    """Returns a valid draft so we measure only orchestration overhead.

    Option A folds validation into the single generation call, so there is just
    one prompt type to answer.
    """

    def __init__(self) -> None:
        self.calls = 0

    async def generate(
        self,
        prompt,
        *,
        temperature,
        response_mime_type=None,
        model=None,
    ):
        self.calls += 1
        return json.dumps(
            {"draft_question": "What integrations are required between modules?"}
        )


@pytest.mark.asyncio
async def test_next_question_under_5s_for_1000_word_input():
    text = " ".join(["payment"] * 1000)
    history = [{"role": "stakeholder", "content": text, "strategy": None}]
    stub = StubLLM()
    gen = QuestionGenerator(llm=stub)

    t0 = time.perf_counter()
    q = await gen.next_question(
        phase="exploration",
        summary="POS for retail",
        history=history,
    )
    elapsed = time.perf_counter() - t0

    print(f"\n[perf] next_question elapsed: {elapsed:.4f}s")
    assert q.valid is True
    assert stub.calls == 1  # single LLM round-trip (Option A)
    assert elapsed < 5.0, f"NFR violated: next_question took {elapsed:.2f}s"
