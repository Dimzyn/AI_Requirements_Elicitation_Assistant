"""Proposes reconciled wording for a detected conflict.

Suggestion only — this never writes the requirement. The requirements engineer
reviews (and edits) the draft, then commits it via PATCH /requirements/{rid}. Mirrors
the JSON-mode shape of `RequirementExtractor`.
"""

import json
from typing import List


class ResolutionSuggester:
    """Drafts a single reconciled requirement from the two conflicting statements,
    the conflict explanation, and the resolution-chat transcript."""

    def __init__(self, *, llm):
        self.llm = llm

    async def suggest(
        self,
        *,
        statement_a: str,
        statement_b: str,
        explanation: str,
        transcript: List[dict],
        same_stakeholder: bool,
    ) -> dict:
        convo = "\n".join(f"{t['role']}: {t['content']}" for t in transcript) or "(no discussion yet)"
        whose = (
            "two requirements from the SAME stakeholder"
            if same_stakeholder
            else "requirements from two DIFFERENT stakeholders"
        )
        prompt = (
            "You are helping a requirements engineer reconcile a conflict between "
            f"{whose}.\n\n"
            f'Requirement A: "{statement_a}"\n'
            f'Requirement B: "{statement_b}"\n'
            f"Why they conflict: {explanation}\n\n"
            "Conversation with the stakeholder(s) about the conflict:\n"
            f"{convo}\n\n"
            "Propose ONE reconciled requirement statement that resolves the "
            "contradiction, honoring whatever direction the conversation settled on "
            "(one side wins, a compromise, or a restatement). Write it as a single "
            "complete sentence of roughly 6 to 25 words, in the same style as the "
            "originals. Then give a one-sentence rationale for the choice.\n\n"
            'Return JSON: {"suggestion": str, "rationale": str}'
        )
        raw = await self.llm.generate(prompt, temperature=0.3, response_mime_type="application/json")
        data = json.loads(raw)
        return {
            "suggestion": (data.get("suggestion") or "").strip(),
            "rationale": (data.get("rationale") or "").strip(),
        }
