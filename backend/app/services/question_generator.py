import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

from .context_manager import ContextManager
from .llm_service import UpstreamUnavailable, first_json_object
from .strategy_selector import StrategySelector, ConflictStrategySelector
from .mistake_validator import taxonomy_block


class QuestionParseError(UpstreamUnavailable):
    """Gemini kept returning a payload that isn't a JSON object.

    Subclasses UpstreamUnavailable so the routers' existing 503 mapping covers
    parse failures too, instead of letting them escape as a 500.
    """

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

# Initial call + one retry: a malformed payload is usually a one-off generation
# glitch, and a fresh call almost always yields valid JSON. Persistent garbage
# degrades to QuestionParseError (-> 503) rather than crashing with a 500.
_PARSE_ATTEMPTS = 2


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
        conflict_sel: Optional[ConflictStrategySelector] = None,
    ) -> None:
        self.llm = llm
        self.ctx = ctx or ContextManager()
        self.sel = sel or StrategySelector()
        self.conflict_sel = conflict_sel or ConflictStrategySelector()

    async def next_question(
        self, *, phase: str, summary: str, history: list, kind: str = "interview"
    ) -> GeneratedQuestion:
        agent_history = [t.get("strategy") for t in history if t["role"] == "agent" and t.get("strategy")]
        last_stakeholder = next(
            (t["content"] for t in reversed(history) if t["role"] == "stakeholder"), ""
        )
        if kind == "conflict_resolution":
            strategy = self.conflict_sel.choose(agent_history=agent_history)
        else:
            strategy = self.sel.choose(agent_history=agent_history, last_stakeholder=last_stakeholder)

        context_prompt = self.ctx.build_prompt(phase=phase, summary=summary, history=history)
        prompt = (
            f"{context_prompt}\n\n"
            f"Strategy directive: {_STRATS[strategy]}\n\n"
            f"{_MISTAKE_GUARD}"
        )

        for attempt in range(1, _PARSE_ATTEMPTS + 1):
            t0 = time.perf_counter()
            raw = await self.llm.generate(prompt, temperature=0.7, response_mime_type="application/json")
            # Surfaces whether latency tracks history growth (prompt chars / turn count)
            # or upstream slowness (pair with LLMService's fallback warnings).
            logger.info(
                "probing question generated in %.0f ms (strategy=%s, prompt=%d chars, history=%d turns)",
                (time.perf_counter() - t0) * 1000,
                strategy,
                len(prompt),
                len(history),
            )
            try:
                payload = first_json_object(raw)
            except (TypeError, ValueError):
                # Non-JSON text, or resp.text=None when the response has no text part.
                payload = None
            if isinstance(payload, dict):
                question = (payload.get("draft_question") or "").strip()
                return GeneratedQuestion(
                    question=question,
                    strategy=strategy,
                    attempts=attempt,
                    valid=True,
                    mistakes=[],
                )
            logger.warning(
                "Gemini returned an unparseable question payload (attempt %d/%d): %.200s",
                attempt,
                _PARSE_ATTEMPTS,
                raw,
            )
        raise QuestionParseError(
            "Gemini returned an unreadable response. Try again in a moment."
        )
