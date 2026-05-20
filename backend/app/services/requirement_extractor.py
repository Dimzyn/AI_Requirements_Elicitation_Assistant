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
            "- Skip vague filler that isn't actionable ('be user-friendly' on its own).\n\n"
            "CLASSIFY BY INTENT, NOT BY KEYWORDS:\n"
            "- functional: a behavior, capability, or feature the user can observe or trigger.\n"
            "    Examples: 'Sync task-complete state to Google Calendar.',\n"
            "              'Drag-and-drop tasks onto calendar slots.',\n"
            "              'Update task visual state on completion.',\n"
            "              'Retry failed syncs in the background.'\n"
            "- non_functional: a MEASURABLE quality with a threshold or metric (time,\n"
            "    percentage, count, standard). NOT just adjectives like 'fast' or 'reliable'.\n"
            "    Examples: 'P95 latency under 3 seconds.',\n"
            "              '99.9% monthly uptime.',\n"
            "              'Support 1000 concurrent users.',\n"
            "              'WCAG 2.1 AA accessibility compliance.'\n"
            "- constraint: an external limitation imposed on the project.\n"
            "    Examples: 'Must integrate with Google Calendar API.',\n"
            "              'Ship before 2026-08-01.',\n"
            "              'Comply with GDPR Article 17.'\n\n"
            "WORDS THAT TRICK YOU — these are qualifiers on a functional behavior, NOT NFRs:\n"
            "  'instantly', 'in background', 'silently', 'fast', 'responsive', 'user-friendly',\n"
            "  'seamless', 'smooth', 'automatic'.\n"
            "A statement is non_functional ONLY if it carries a verifiable threshold. So:\n"
            "  'Update UI instantly when task is checked.'  -> functional (behavior).\n"
            "  'Update UI within 100ms of task check.'      -> non_functional (metric).\n"
            "  'Sync to Google Calendar in background.'     -> functional (capability).\n"
            "  '99.9% of syncs succeed within 5s.'          -> non_functional (metric).\n\n"
            "Return JSON: {\"requirements\": [{\"statement\": str, \"type\": str}]}\n\n"
            f"Text:\n\"\"\"{stakeholder_text}\"\"\""
        )
        raw = await self.llm.generate(prompt, temperature=0.2, response_mime_type="application/json")
        return json.loads(raw).get("requirements", [])
