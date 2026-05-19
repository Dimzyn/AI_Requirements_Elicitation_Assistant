from pathlib import Path
from typing import Iterable

_TEMPLATE = (
    Path(__file__).parent.parent / "prompts" / "context_prompt.txt"
).read_text(encoding="utf-8")


class ContextManager:
    """Builds a Least-to-Most prompt from session phase, running summary, and dialogue history."""

    def build_prompt(self, *, phase: str, summary: str, history: Iterable[dict]) -> str:
        lines = [f"{t['role']}: {t['content']}" for t in history]
        return _TEMPLATE.format(
            phase=phase,
            summary=summary or "(none)",
            history="\n".join(lines) or "(empty)",
        )
