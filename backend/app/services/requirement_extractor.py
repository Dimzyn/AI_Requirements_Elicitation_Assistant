import json
from typing import List


class RequirementExtractor:
    """Extracts atomic requirement statements from stakeholder text via JSON-mode Gemini call."""

    def __init__(self, *, llm):
        self.llm = llm

    async def extract(self, stakeholder_text: str) -> List[dict]:
        prompt = (
            "Extract distinct, testable requirements from the stakeholder text below.\n\n"
            "Rules:\n"
            "- One requirement = one user-visible capability or constraint. Combine multi-step "
            "interactions (e.g. drag-and-drop, search-and-filter, login-with-OTP) into a single "
            "requirement. Do NOT split on every verb or conjunction.\n"
            "- Deduplicate: if two phrasings describe the same capability, keep only one.\n"
            "- Skip vague filler that isn't actionable (e.g. 'be user-friendly' on its own).\n"
            "- Classify each as: functional (features/capabilities), non_functional "
            "(performance, security, usability, reliability), or constraint (technology, "
            "deadline, budget, regulatory).\n\n"
            "Return JSON: {\"requirements\": [{\"statement\": str, \"type\": str}]}\n\n"
            f"Text:\n\"\"\"{stakeholder_text}\"\"\""
        )
        raw = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
        return json.loads(raw).get("requirements", [])
