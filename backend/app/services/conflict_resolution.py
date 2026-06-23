"""Builders for the AI-opened conflict-resolution chat.

Pure, dependency-free helpers (mirrors `_greeting` in routers/sessions.py and the
frontend `contactMessage.ts`). The *opener* is the agent's first chat turn shown
to the stakeholder; the *summary* is stored on the session and fed to the existing
QuestionGenerator so its follow-up questions stay focused on the conflict.
"""


def _first_name(name: str | None) -> str:
    first = (name or "").strip().split(" ")[0]
    return first or "there"


def _project_label(title: str | None) -> str:
    trimmed = (title or "").strip()
    return trimmed or "this project"


def build_resolution_opener(
    *,
    stakeholder_name: str | None,
    their_statement: str,
    other_statement: str,
    explanation: str,
    project_title: str | None,
) -> str:
    """Opener for a conflict between this stakeholder and a different one."""
    return "\n".join(
        [
            f"Hi {_first_name(stakeholder_name)} 👋 Thanks for helping shape "
            f"{_project_label(project_title)}.",
            "",
            "One thing you asked for seems to clash with what another stakeholder "
            "needs, and I'd love your help reconciling it:",
            "",
            f'• What you asked for: "{their_statement}"',
            f'• What conflicts with it: "{other_statement}"',
            "",
            f"Why they can't both hold: {explanation}",
            "",
            "How would you like to resolve this — should one take priority, is there "
            "a middle ground, or did I misread what you need?",
        ]
    )


def build_self_resolution_opener(
    *,
    stakeholder_name: str | None,
    statement_a: str,
    statement_b: str,
    explanation: str,
    project_title: str | None,
) -> str:
    """Opener for a conflict between two requirements from the SAME stakeholder."""
    return "\n".join(
        [
            f"Hi {_first_name(stakeholder_name)} 👋 Thanks for helping shape "
            f"{_project_label(project_title)}.",
            "",
            "Two things you mentioned seem to pull in different directions, and I'd "
            "love your help reconciling them:",
            "",
            f'• "{statement_a}"',
            f'• "{statement_b}"',
            "",
            f"Why they can't both hold: {explanation}",
            "",
            "How would you like to resolve this — should one take priority, is there "
            "a middle ground, or did I misstate something?",
        ]
    )


def build_resolution_summary(
    *,
    their_statement: str,
    other_statement: str,
    explanation: str,
    same_stakeholder: bool,
) -> str:
    """Context string stored on the session so QuestionGenerator stays on-topic."""
    whose = (
        "Two of the stakeholder's own requirements contradict each other."
        if same_stakeholder
        else "The stakeholder's requirement conflicts with another stakeholder's."
    )
    return (
        "This is a conflict-resolution conversation. " + whose + " Your job is to "
        "help the stakeholder resolve the contradiction.\n\n"
        "Conflicting requirements:\n"
        f'- "{their_statement}"\n'
        f'- "{other_statement}"\n'
        f"Why they conflict: {explanation}\n\n"
        "Focus every question on reconciling THIS specific conflict: clarify intent, "
        "surface which need matters more, and steer toward a concrete resolution "
        "(one wins, a compromise, or a restatement). Do not open a broad new "
        "elicitation on unrelated topics."
    )
