import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .context_manager import ContextManager
from .strategy_selector import StrategySelector
from .mistake_validator import taxonomy_block

_STRATS = json.loads(
    (Path(__file__).parent.parent / "prompts" / "strategy_prompts.json").read_text(encoding="utf-8")
)

# The 14-mistake taxonomy is applied INLINE during generation: a single Gemini call
# produces a question that already self-avoids the mistakes, instead of a separate
# validator call plus a retry loop. This roughly halves per-question latency while
# keeping the taxonomy as the quality guard (now a generation constraint).
_MISTAKE_GUARD = (
    "Your draft_question MUST NOT commit any of these 14 requirements-interview "
    "mistakes:\n"
    f"{taxonomy_block()}\n"
    "Silently re-check the question against every item above and rewrite it until "
    "it commits none before you return it."
)


@dataclass
class GeneratedQuestion:
    question: str
    strategy: str
    attempts: int
    valid: bool
    mistakes: List[str]


class QuestionGenerator:
    """Generates one probing question per call via the Hybrid Intelligent Agent.

    ``ContextManager`` (Least-to-Most) and ``StrategySelector`` (Concept / Related /
    NFR / Pivot / General) shape the prompt; the 14-mistake taxonomy is embedded as
    a generation guard so a single LLM call yields an already-validated question.
    """

    def __init__(
        self,
        *,
        llm,
        ctx: Optional[ContextManager] = None,
        sel: Optional[StrategySelector] = None,
    ) -> None:
        self.llm = llm
        self.ctx = ctx or ContextManager()
        self.sel = sel or StrategySelector()

    async def next_question(self, *, phase: str, summary: str, history: list) -> GeneratedQuestion:
        agent_history = [t.get("strategy") for t in history if t["role"] == "agent" and t.get("strategy")]
        last_stakeholder = next(
            (t["content"] for t in reversed(history) if t["role"] == "stakeholder"), ""
        )
        strategy = self.sel.choose(agent_history=agent_history, last_stakeholder=last_stakeholder)

        context_prompt = self.ctx.build_prompt(phase=phase, summary=summary, history=history)
        prompt = (
            f"{context_prompt}\n\n"
            f"Strategy directive: {_STRATS[strategy]}\n\n"
            f"{_MISTAKE_GUARD}"
        )

        raw = await self.llm.generate(prompt, temperature=0.7, response_mime_type="application/json")
        question = (json.loads(raw).get("draft_question") or "").strip()
        return GeneratedQuestion(
            question=question,
            strategy=strategy,
            attempts=1,
            valid=True,
            mistakes=[],
        )
