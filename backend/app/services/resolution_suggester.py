"""Proposes reconciled wording for a detected conflict.

Suggestion only — this never writes the requirement. The requirements engineer
reviews (and edits) the draft, then commits it via PATCH /requirements/{rid}. Mirrors
the JSON-mode shape of `RequirementExtractor`.
"""

from typing import List

from .llm_service import UpstreamUnavailable, first_json_object


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
        resolutions: List[dict] | None = None,
    ) -> dict:
        convo = "\n".join(f"{t['role']}: {t['content']}" for t in transcript) or "(no discussion yet)"
        stances = "\n".join(
            f"- {s.get('decision')}: {s.get('statement') or '(no wording)'}" for s in (resolutions or [])
        ) or "(none captured)"
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
            "Captured stakeholder resolution stance(s):\n"
            f"{stances}\n\n"
            "Conversation with the stakeholder(s) about the conflict:\n"
            f"{convo}\n\n"
            "Propose ONE reconciled requirement statement that resolves the "
            "contradiction, honoring whatever direction the conversation and the "
            "captured stance(s) settled on (one side wins, a compromise, or a "
            "restatement). Write it as a single complete sentence of roughly 6 to 25 "
            "words, in the same style as the originals. Then give a one-sentence "
            "rationale for the choice.\n\n"
            'Return JSON: {"suggestion": str, "rationale": str}'
        )
        raw = await self.llm.generate(prompt, temperature=0.3, response_mime_type="application/json")
        try:
            data = first_json_object(raw)
        except (ValueError, TypeError) as exc:
            # The suggest endpoint maps UpstreamUnavailable to a 503 "try again";
            # an unreadable payload is transient the same way an overload is.
            raise UpstreamUnavailable(
                "Gemini returned an unreadable response. Try again in a moment."
            ) from exc
        return {
            "suggestion": (data.get("suggestion") or "").strip(),
            "rationale": (data.get("rationale") or "").strip(),
        }
