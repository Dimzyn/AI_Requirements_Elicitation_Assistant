from typing import List


class StrategySelector:
    """Chooses the next probing strategy.

    Strategies: concept / related_concept / general / nfr_probe / pivot
    """

    SHORT_REPLY_TOKEN_THRESHOLD = 8
    NFR_PROBE_EVERY = 4         # every Nth agent turn is an NFR probe
    DRILL_PIVOT_AFTER = 3       # 3 consecutive concept/related turns -> force pivot

    _DRILL_STRATS = {"concept", "related_concept"}

    def choose(self, *, agent_history: List[str], last_stakeholder: str) -> str:
        if not agent_history:
            return "concept"

        if len(last_stakeholder.split()) < self.SHORT_REPLY_TOKEN_THRESHOLD:
            return "general"

        next_turn_index = len(agent_history) + 1
        if next_turn_index % self.NFR_PROBE_EVERY == 0:
            return "nfr_probe"

        tail = agent_history[-self.DRILL_PIVOT_AFTER:]
        if len(tail) == self.DRILL_PIVOT_AFTER and all(s in self._DRILL_STRATS for s in tail):
            return "pivot"

        if agent_history[-2:] == ["concept", "concept"]:
            return "related_concept"

        return "related_concept" if agent_history[-1] == "concept" else "concept"
