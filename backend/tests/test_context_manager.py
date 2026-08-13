from app.services.context_manager import ContextManager


def test_builds_prompt_with_phase_and_history():
    cm = ContextManager()
    out = cm.build_prompt(
        phase="exploration",
        summary="System for online payments.",
        history=[{"role": "stakeholder", "content": "I want a payment app."}],
    )
    assert "exploration" in out
    assert "I want a payment app." in out
    # The template should leave a literal JSON spec line for the LLM to follow:
    assert "draft_question" in out


def test_empty_history_renders_placeholder():
    cm = ContextManager()
    out = cm.build_prompt(phase="exploration", summary="", history=[])
    assert "(none)" in out  # summary placeholder
    assert "(empty)" in out  # history placeholder


def test_history_preserves_order_and_role():
    cm = ContextManager()
    out = cm.build_prompt(
        phase="deepening",
        summary="s",
        history=[
            {"role": "stakeholder", "content": "A"},
            {"role": "agent", "content": "B"},
            {"role": "stakeholder", "content": "C"},
        ],
    )
    # Each line "role: content" appears in order
    a_idx = out.index("stakeholder: A")
    b_idx = out.index("agent: B")
    c_idx = out.index("stakeholder: C")
    assert a_idx < b_idx < c_idx


def test_history_capped_to_recent_turns_with_omission_marker():
    cm = ContextManager()
    history = [{"role": "stakeholder", "content": f"turn-{i}"} for i in range(15)]
    out = cm.build_prompt(phase="exploration", summary="s", history=history)
    # Only the last 12 turns survive; the 3 oldest are replaced by a marker.
    assert "(3 earlier turns omitted)" in out
    for i in range(3):
        assert f"turn-{i}\n" not in out and not out.endswith(f"turn-{i}")
    for i in range(3, 15):
        assert f"turn-{i}" in out


def test_no_omission_marker_when_history_fits():
    cm = ContextManager()
    history = [{"role": "stakeholder", "content": f"turn-{i}"} for i in range(12)]
    out = cm.build_prompt(phase="exploration", summary="s", history=history)
    assert "omitted" not in out
    for i in range(12):
        assert f"turn-{i}" in out


def test_requirements_block_rendered():
    cm = ContextManager()
    out = cm.build_prompt(
        phase="exploration",
        summary="s",
        history=[],
        requirements=["The system shall support meal-card payment.", "Delivery under 20 minutes."],
    )
    assert "The system shall support meal-card payment." in out
    assert "Delivery under 20 minutes." in out


def test_requirements_default_placeholder():
    cm = ContextManager()
    out = cm.build_prompt(phase="exploration", summary="s", history=[])
    assert "(none yet)" in out
