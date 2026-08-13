from pathlib import Path
from typing import Iterable, Optional

_TEMPLATE = (
    Path(__file__).parent.parent / "prompts" / "context_prompt.txt"
).read_text(encoding="utf-8")

# Only the most recent turns enter the prompt. Older ground is carried by the
# extracted-requirements block instead, so prompt size (and with it Gemini
# latency) plateaus rather than growing with the transcript.
_MAX_PROMPT_TURNS = 12


class ContextManager:
    """Builds a Least-to-Most prompt from session phase, running summary, and dialogue history."""

    def build_prompt(
        self,
        *,
        phase: str,
        summary: str,
        history: Iterable[dict],
        requirements: Optional[list[str]] = None,
    ) -> str:
        turns = list(history)
        omitted = len(turns) - _MAX_PROMPT_TURNS
        lines = [f"{t['role']}: {t['content']}" for t in turns[-_MAX_PROMPT_TURNS:]]
        if omitted > 0:
            lines.insert(0, f"({omitted} earlier turns omitted)")
        return _TEMPLATE.format(
            phase=phase,
            summary=summary or "(none)",
            requirements="\n".join(f"- {r}" for r in requirements) if requirements else "(none yet)",
            history="\n".join(lines) or "(empty)",
        )
