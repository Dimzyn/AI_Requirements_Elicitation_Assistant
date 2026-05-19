import json
from typing import List


class RequirementExtractor:
    """Extracts atomic requirement statements from stakeholder text via JSON-mode Gemini call."""

    def __init__(self, *, llm):
        self.llm = llm

    async def extract(self, stakeholder_text: str) -> List[dict]:
        prompt = (
            "Extract atomic, testable requirements from the stakeholder text below. "
            "Classify each as functional, non_functional, or constraint. "
            "Return JSON: {\"requirements\": [{\"statement\": str, \"type\": str}]}\n"
            f"Text:\n\"\"\"{stakeholder_text}\"\"\""
        )
        raw = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
        return json.loads(raw).get("requirements", [])
