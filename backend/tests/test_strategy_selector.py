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


def test_nfr_probe_injected_every_fourth_turn():
    sel = StrategySelector()
    # next turn is the 4th -> nfr_probe
    assert sel.choose(
        agent_history=["concept", "related_concept", "concept"],
        last_stakeholder="Cashiers need to ring up sales quickly during peak hours.",
    ) == "nfr_probe"


def test_nfr_probe_injected_on_eighth_turn():
    sel = StrategySelector()
    # 7 prior agent turns -> next is the 8th
    assert sel.choose(
        agent_history=["concept", "related_concept", "concept", "nfr_probe", "concept", "related_concept", "concept"],
        last_stakeholder="Managers also need to view reconciliation reports across all outlets.",
    ) == "nfr_probe"


def test_pivot_after_three_drill_turns():
    sel = StrategySelector()
    # 3 consecutive concept/related (no nfr_probe in the tail) and next slot is
    # NOT divisible by 4 -> pivot
    assert sel.choose(
        agent_history=["general", "concept", "related_concept", "concept"],
        last_stakeholder="The mobile app must also handle session timeouts gracefully when the network drops.",
    ) == "pivot"


def test_nfr_probe_takes_priority_over_pivot():
    sel = StrategySelector()
    # last three are drill candidates AND next turn is 4th -> nfr_probe wins
    assert sel.choose(
        agent_history=["concept", "related_concept", "concept"],
        last_stakeholder="The cashier UI must also handle returns and exchanges in a single workflow.",
    ) == "nfr_probe"


def test_short_reply_takes_priority_over_nfr_and_pivot():
    sel = StrategySelector()
    assert sel.choose(
        agent_history=["concept", "related_concept", "concept"],
        last_stakeholder="Yes.",
    ) == "general"
