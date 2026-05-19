from typing import List


class StrategySelector:
    """Chooses the next probing-question strategy: concept / related_concept / general."""

    SHORT_REPLY_TOKEN_THRESHOLD = 8

    def choose(self, *, agent_history: List[str], last_stakeholder: str) -> str:
        if not agent_history:
            return "concept"
        if len(last_stakeholder.split()) < self.SHORT_REPLY_TOKEN_THRESHOLD:
            return "general"
        if agent_history[-2:] == ["concept", "concept"]:
            return "related_concept"
        return "related_concept" if agent_history[-1] == "concept" else "concept"
