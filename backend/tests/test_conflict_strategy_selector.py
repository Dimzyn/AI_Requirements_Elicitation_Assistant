import json
from pathlib import Path

from app.services.strategy_selector import ConflictStrategySelector

_PROMPTS = json.loads(
    (Path("app") / "prompts" / "strategy_prompts.json").read_text(encoding="utf-8")
)


def test_first_probe_clarifies_first_requirement():
    assert ConflictStrategySelector().choose(agent_history=[]) == "clarify_intent_a"


def test_progression_advances_by_prior_conflict_turns():
    sel = ConflictStrategySelector()
    assert sel.choose(agent_history=["clarify_intent_a"]) == "clarify_intent_b"
    assert sel.choose(agent_history=["clarify_intent_a", "clarify_intent_b"]) == "weigh_priority"
    assert sel.choose(
        agent_history=["clarify_intent_a", "clarify_intent_b", "weigh_priority"]
    ) == "explore_middle_ground"
    assert sel.choose(
        agent_history=["clarify_intent_a", "clarify_intent_b", "weigh_priority", "explore_middle_ground"]
    ) == "confirm_resolution"


def test_holds_on_confirm_after_progression_exhausted():
    sel = ConflictStrategySelector()
    assert sel.choose(agent_history=["a", "b", "c", "d", "e"]) == "confirm_resolution"
    assert sel.choose(agent_history=["a", "b", "c", "d", "e", "f", "g"]) == "confirm_resolution"


def test_all_five_conflict_prompts_exist():
    for key in (
        "clarify_intent_a",
        "clarify_intent_b",
        "weigh_priority",
        "explore_middle_ground",
        "confirm_resolution",
    ):
        assert key in _PROMPTS and _PROMPTS[key].strip()
