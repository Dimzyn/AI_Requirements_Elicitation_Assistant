"""Detects whether a conflict-resolution chat has reached a resolution.

JSON-mode Gemini call (mirrors RequirementExtractor). Returns a structured stance
relative to the conflict's canonical requirement A / requirement B, or a
not-reached result on any ambiguity or parse failure — the caller treats a
not-reached result as "keep probing".
"""

import json
from typing import List

_VALID_DECISIONS = {"a_wins", "b_wins", "compromise", "restate"}
_NOT_REACHED = {"reached": False, "decision": None, "statement": None}


class ResolutionTracker:
    def __init__(self, *, llm):
        self.llm = llm

    async def track(
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
            "You are analysing a conversation in which a requirements engineer's AI is "
            f"helping resolve a conflict between {whose}.\n\n"
            f'Requirement A: "{statement_a}"\n'
            f'Requirement B: "{statement_b}"\n'
            f"Why they conflict: {explanation}\n\n"
            "Conversation so far:\n"
            f"{convo}\n\n"
            "Decide whether the stakeholder has clearly SETTLED on how to resolve the "
            "conflict. Only say reached=true when the direction is unambiguous — not when "
            "they are still weighing options or asking questions.\n"
            "Classify the resolution relative to requirement A and requirement B above:\n"
            '- "a_wins": requirement A takes priority; B is dropped or overridden.\n'
            '- "b_wins": requirement B takes priority; A is dropped or overridden.\n'
            '- "compromise": both are partly satisfied (e.g. scoped by context or threshold).\n'
            '- "restate": the stakeholder reworded the need into a single new requirement.\n'
            "When reached=true, give 'statement': one complete sentence (6-25 words) that "
            "states the resolved requirement in the same style as the originals. When "
            "reached=false, set decision and statement to null.\n\n"
            'Return JSON: {"reached": bool, "decision": "a_wins"|"b_wins"|"compromise"|"restate"|null, "statement": str|null}'
        )
        try:
            raw = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            return dict(_NOT_REACHED)

        decision = data.get("decision")
        if not data.get("reached") or decision not in _VALID_DECISIONS:
            return dict(_NOT_REACHED)
        statement = (data.get("statement") or "").strip() or None
        return {"reached": True, "decision": decision, "statement": statement}
