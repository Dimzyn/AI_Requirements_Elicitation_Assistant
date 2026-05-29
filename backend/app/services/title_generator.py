DEFAULT_TITLE = "New conversation"


class TitleGenerator:
    """Generates a short, human-readable session title from the first stakeholder message."""

    def __init__(self, *, llm):
        self.llm = llm

    async def generate(self, stakeholder_text: str) -> str:
        prompt = (
            "Generate a short, descriptive project title (2 to 5 words) for the "
            "software described below.\n"
            "Output ONLY the title text — no surrounding quotes, no trailing "
            "punctuation, no 'Title:' prefix.\n\n"
            "Examples:\n"
            "  Input: 'I want an app to sync my to-do list with Google Calendar.'\n"
            "  Title: Calendar Task Sync\n"
            "  Input: 'A point of sale system for my coffee shop.'\n"
            "  Title: Coffee Shop POS\n\n"
            f"Description:\n\"\"\"{stakeholder_text}\"\"\""
        )
        raw = await self.llm.generate(prompt, temperature=0.3)
        title = " ".join((raw or "").split())  # collapse newlines / runs of whitespace
        title = title.strip(" \"'.!,;:")  # drop wrapping quotes and trailing punctuation
        if not title:
            return DEFAULT_TITLE
        words = title.split()
        if len(words) > 6:
            title = " ".join(words[:6])
        return title[:60]
