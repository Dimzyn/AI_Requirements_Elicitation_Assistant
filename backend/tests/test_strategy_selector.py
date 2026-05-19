from app.services.strategy_selector import StrategySelector


def test_first_turn_is_concept():
    sel = StrategySelector()
    assert sel.choose(agent_history=[], last_stakeholder="I want a chat app for clinicians.") == "concept"


def test_short_reply_triggers_general():
    sel = StrategySelector()
    assert sel.choose(agent_history=["concept"], last_stakeholder="Yes.") == "general"


def test_two_concepts_force_related():
    sel = StrategySelector()
    assert sel.choose(
        agent_history=["concept", "concept"],
        last_stakeholder="It should support payments via card and wallet for retail.",
    ) == "related_concept"


def test_round_robin_after_related():
    sel = StrategySelector()
    assert sel.choose(
        agent_history=["concept", "related_concept"],
        last_stakeholder="The system also needs to track refunds and chargebacks for compliance.",
    ) == "concept"


def test_round_robin_after_concept_when_not_two_in_row():
    sel = StrategySelector()
    assert sel.choose(
        agent_history=["general", "concept"],
        last_stakeholder="Users include cashiers, store managers, and accountants across multiple retail outlets.",
    ) == "related_concept"
