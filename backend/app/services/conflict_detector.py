from typing import List

from .llm_service import first_json_object


class ConflictDetector:
    """Finds pairs of directly contradicting requirements via a single JSON-mode Gemini call.

    Input requirements are dicts: {"id": str, "statement": str, "stakeholder": str|None, "type": str}.
    Output pairs are dicts: {"requirement_a": str, "requirement_b": str, "explanation": str},
    where requirement_a/_b are the original ids, sorted so requirement_a <= requirement_b.
    """

    def __init__(self, *, llm):
        self.llm = llm

    async def detect(self, requirements: List[dict]) -> List[dict]:
        if len(requirements) < 2:
            return []

        numbered = "\n".join(
            f'{i}. [{r.get("stakeholder") or "Unknown"}] {r["statement"]}'
            for i, r in enumerate(requirements)
        )

        prompt = (
            "You are reviewing software requirements gathered from MULTIPLE stakeholders.\n"
            "Each line is numbered and tagged with the stakeholder who stated it:\n"
            "    <index>. [<stakeholder>] <requirement>\n\n"
            "Find pairs of requirements that DIRECTLY CONTRADICT each other — pairs that\n"
            "cannot both be satisfied in the same system (e.g. 'auto-approve refunds' vs\n"
            "'all refunds require manager sign-off').\n\n"
            "STRICT RULES:\n"
            "- Report ONLY direct contradictions. Do NOT report requirements that are merely\n"
            "  different, related, overlapping, redundant, or vague. If two requirements can\n"
            "  both hold at once, they are NOT a conflict.\n"
            "- Prefer precision: when in doubt, do NOT report a pair.\n"
            "- Reference requirements by their integer index from the list.\n"
            "- Each explanation is ONE sentence stating why the two cannot coexist.\n\n"
            'Return JSON: {"conflicts": [{"a": <int>, "b": <int>, "explanation": <str>}]}\n'
            "If there are no contradictions, return an empty list.\n\n"
            f"Requirements:\n{numbered}"
        )

        raw = await self.llm.generate(
            prompt, temperature=0.2, response_mime_type="application/json"
        )
        try:
            payload = first_json_object(raw)
        except (ValueError, TypeError):
            return []
        # Degrade any off-contract shape (list payload, non-list "conflicts") to
        # "none found" — detection is best-effort and must never 500 the endpoint.
        if not isinstance(payload, dict):
            return []
        pairs = payload.get("conflicts", [])
        if not isinstance(pairs, list):
            return []

        n = len(requirements)
        seen: set[tuple[str, str]] = set()
        out: List[dict] = []
        for p in pairs:
            if not isinstance(p, dict):
                continue
            a = p.get("a")
            b = p.get("b")
            if not isinstance(a, int) or not isinstance(b, int):
                continue
            if a == b or not (0 <= a < n) or not (0 <= b < n):
                continue
            id_a = requirements[a]["id"]
            id_b = requirements[b]["id"]
            key = tuple(sorted((id_a, id_b)))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "requirement_a": key[0],
                    "requirement_b": key[1],
                    "explanation": p.get("explanation") or "",
                }
            )
        return out
