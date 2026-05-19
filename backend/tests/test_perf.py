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
    """Returns valid drafts and valid-verdicts to keep the loop to one attempt.

    Discriminates validator prompts from draft prompts by the word "mistake",
    which only appears in MistakeValidator._build_prompt (strategy prompts and
    the context template do not contain it).
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
        if "mistake" in prompt.lower() or "taxonomy" in prompt.lower():
            return json.dumps({"valid": True, "mistakes": [], "correction": ""})
        return json.dumps(
            {"draft_question": "What integrations are required between modules?"}
        )


@pytest.mark.asyncio
async def test_next_question_under_5s_for_1000_word_input():
    text = " ".join(["payment"] * 1000)
    history = [{"role": "stakeholder", "content": text, "strategy": None}]
    gen = QuestionGenerator(llm=StubLLM())

    t0 = time.perf_counter()
    q = await gen.next_question(
        phase="exploration",
        summary="POS for retail",
        history=history,
    )
    elapsed = time.perf_counter() - t0

    print(f"\n[perf] next_question elapsed: {elapsed:.4f}s")
    assert q.valid is True
    assert elapsed < 5.0, f"NFR violated: next_question took {elapsed:.2f}s"
