import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

_TAX = json.loads(
    (Path(__file__).parent.parent / "prompts" / "mistake_taxonomy.json").read_text(encoding="utf-8")
)


@dataclass
class Verdict:
    valid: bool
    mistakes: List[str]
    correction: str


class MistakeValidator:
    """Sends a candidate probing question to the LLM and parses a JSON verdict."""

    def __init__(self, *, llm, max_retries: int = 3) -> None:
        self.llm = llm
        # max_retries lives on the validator for callers that want to read it,
        # but the validator itself does NOT loop — the orchestrator (Task 4.5) does.
        self.max_retries = max_retries

    def _build_prompt(self, draft: str) -> str:
        mistakes_block = "\n".join(f"- {m['id']}: {m['desc']}" for m in _TAX["mistakes"])
        return (
            "You are a strict requirements-interview reviewer.\n"
            f"Given the candidate probing question:\n\"\"\"{draft}\"\"\"\n"
            "Decide whether it commits any of these 14 mistakes:\n"
            f"{mistakes_block}\n\n"
            "Respond with JSON: "
            "{\"valid\": bool, \"mistakes\": [ids], \"correction\": <suggested rewrite or empty>}"
        )

    async def validate(self, draft: str) -> Verdict:
        raw = await self.llm.generate(
            self._build_prompt(draft),
            temperature=0.1,
            response_mime_type="application/json",
        )
        data = json.loads(raw)
        return Verdict(
            valid=bool(data.get("valid")),
            mistakes=list(data.get("mistakes", [])),
            correction=str(data.get("correction", "")),
        )
