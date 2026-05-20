import json
from typing import List


class RequirementExtractor:
    """Extracts atomic requirement statements from stakeholder text via JSON-mode Gemini call."""

    def __init__(self, *, llm):
        self.llm = llm

    async def extract(self, stakeholder_text: str) -> List[dict]:
        prompt = (
            "Extract distinct, testable requirements from the stakeholder text below.\n\n"
            "STYLE — write each statement like a developer ticket title:\n"
            "- 5 to 15 words. Prefer the shortest phrasing that still captures the intent.\n"
            "- Lead with the action or noun. Drop ceremonial openers like 'The system shall',\n"
            "  'The application shall be able to', 'Users shall be able to'.\n"
            "- Use plain, direct language. No nested clauses unless essential.\n"
            "- Examples of GOOD phrasing:\n"
            "    'Sync to-do items with Google Calendar.'\n"
            "    'Auto-reschedule overdue time-blocked tasks to the next free slot.'\n"
            "    'Drag-and-drop pending tasks onto calendar slots.'\n"
            "    'P95 latency under 3 seconds.'\n"
            "- Examples of BAD phrasing (too long / too ceremonial):\n"
            "    'The application shall allow users to create and manage to-do list items "
            "that are tracked within Google Calendar.'\n"
            "    'The system shall automatically suggest moving a time-blocked task to the "
            "next available block of free time if it is not checked off by the end of its "
            "allotted window.'\n\n"
            "CONTENT RULES:\n"
            "- One requirement = one user-visible capability or constraint. Combine multi-step "
            "interactions (drag-and-drop, search-and-filter, login-with-OTP) into a single line.\n"
            "- Deduplicate: if two phrasings describe the same capability, keep only one.\n"
            "- Skip vague filler that isn't actionable ('be user-friendly' on its own).\n"
            "- Classify each as: functional (features/capabilities), non_functional "
            "(performance, security, usability, reliability), or constraint (technology, "
            "deadline, budget, regulatory).\n\n"
            "Return JSON: {\"requirements\": [{\"statement\": str, \"type\": str}]}\n\n"
            f"Text:\n\"\"\"{stakeholder_text}\"\"\""
        )
        raw = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
        return json.loads(raw).get("requirements", [])
