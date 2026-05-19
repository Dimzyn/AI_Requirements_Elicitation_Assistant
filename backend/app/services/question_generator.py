import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .context_manager import ContextManager
from .strategy_selector import StrategySelector
from .mistake_validator import MistakeValidator

_STRATS = json.loads(
    (Path(__file__).parent.parent / "prompts" / "strategy_prompts.json").read_text(encoding="utf-8")
)


@dataclass
class GeneratedQuestion:
    question: str
    strategy: str
    attempts: int
    valid: bool
    mistakes: List[str]


class QuestionGenerator:
    """Orchestrates draft -> validate -> (retry) loop using the Hybrid Intelligent Agent."""

    def __init__(
        self,
        *,
        llm,
        max_retries: int = 3,
        ctx: Optional[ContextManager] = None,
        sel: Optional[StrategySelector] = None,
        val: Optional[MistakeValidator] = None,
    ) -> None:
        self.llm = llm
        self.max_retries = max_retries
        self.ctx = ctx or ContextManager()
        self.sel = sel or StrategySelector()
        self.val = val or MistakeValidator(llm=llm, max_retries=max_retries)

    async def _draft(self, prompt: str, *, temperature: float) -> str:
        raw = await self.llm.generate(
            prompt,
            temperature=temperature,
            response_mime_type="application/json",
        )
        return json.loads(raw)["draft_question"]

    async def next_question(self, *, phase: str, summary: str, history: list) -> GeneratedQuestion:
        agent_history = [t.get("strategy") for t in history if t["role"] == "agent" and t.get("strategy")]
        last_stakeholder = next((t["content"] for t in reversed(history) if t["role"] == "stakeholder"), "")
        strategy = self.sel.choose(agent_history=agent_history, last_stakeholder=last_stakeholder)
        context_prompt = self.ctx.build_prompt(phase=phase, summary=summary, history=history)
        prompt = f"{context_prompt}\n\nStrategy directive: {_STRATS[strategy]}"

        draft = await self._draft(prompt, temperature=0.7)
        attempts = 1
        verdict = await self.val.validate(draft)

        while not verdict.valid and attempts < self.max_retries:
            attempts += 1
            correction_prompt = (
                f"{prompt}\n\n"
                f"The previous draft was: \"{draft}\".\n"
                f"It committed these mistakes: {verdict.mistakes}.\n"
                f"Apply this correction: {verdict.correction}\n"
                "Return JSON with the corrected draft_question."
            )
            draft = await self._draft(correction_prompt, temperature=0.1)
            verdict = await self.val.validate(draft)

        return GeneratedQuestion(
            question=draft,
            strategy=strategy,
            attempts=attempts,
            valid=verdict.valid,
            mistakes=verdict.mistakes,
        )
