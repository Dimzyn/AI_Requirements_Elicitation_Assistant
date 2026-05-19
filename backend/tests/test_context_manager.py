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
