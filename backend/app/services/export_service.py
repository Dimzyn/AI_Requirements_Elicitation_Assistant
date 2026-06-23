from typing import Iterable

_TYPE_TITLES = {
    "functional": "Functional Requirements",
    "non_functional": "Non-Functional Requirements",
    "constraint": "Constraints",
}


def compile_markdown(*, project_title: str, requirements: Iterable[dict]) -> str:
    buckets: dict[str, list[str]] = {k: [] for k in _TYPE_TITLES}
    for r in requirements:
        buckets.setdefault(r["type"], []).append(r["statement"])
    parts = [f"# Requirements: {project_title}\n"]
    for key, title in _TYPE_TITLES.items():
        items = buckets.get(key) or []
        if items:
            parts.append(f"## {title}\n")
            parts.extend(f"- {s}" for s in items)
            parts.append("")
    return "\n".join(parts)


# Section order, heading, and id-prefix for the IEEE-830-style SRS document.
_SRS_SECTIONS = (
    ("functional", "2.1 Functional Requirements", "FR"),
    ("non_functional", "2.2 Non-Functional Requirements", "NFR"),
    ("constraint", "2.3 Constraints", "CON"),
)

_PRIORITY_LABELS = {"must": "Must", "should": "Should", "could": "Could", "wont": "Won't"}


def _srs_meta(r: dict) -> str:
    """Build the italic sub-line (priority / source / acceptance) for one requirement."""
    parts: list[str] = []
    priority = r.get("priority")
    if priority:
        parts.append(f"Priority: {_PRIORITY_LABELS.get(priority, priority)}")
    stakeholder = r.get("stakeholder")
    if stakeholder:
        parts.append(f"Source: {stakeholder}")
    acceptance = (r.get("acceptance_criteria") or "").strip()
    if acceptance:
        parts.append(f"Acceptance: {acceptance}")
    return " · ".join(parts)


def _bucket_requirements(requirements: Iterable[dict]) -> dict[str, list[dict]]:
    """Group non-rejected requirements by type, preserving section order."""
    by_type: dict[str, list[dict]] = {key: [] for key, _, _ in _SRS_SECTIONS}
    for r in requirements:
        if r.get("status") == "rejected":
            continue
        by_type.setdefault(r.get("type", "functional"), []).append(r)
    return by_type


def compile_srs(
    *,
    project_title: str,
    project_background: str | None = None,
    project_scope: str | None = None,
    requirements: Iterable[dict],
) -> str:
    """Compile an IEEE-830-style SRS document (Markdown) from curated requirements.

    Each requirement dict may carry: statement, type, stakeholder, priority,
    status, acceptance_criteria. Requirements with status "rejected" are omitted,
    and the three requirement sections are numbered (FR-1, NFR-1, CON-1, …).
    """
    by_type = _bucket_requirements(requirements)

    lines: list[str] = [
        f"# Software Requirements Specification — {project_title}",
        "",
        "## 1. Introduction",
        "",
        "### 1.1 Purpose",
        f"This document specifies the software requirements for {project_title}, "
        "compiled from AI-assisted stakeholder interviews.",
        "",
        "### 1.2 Background",
        (project_background or "").strip() or "_Not specified._",
        "",
        "### 1.3 Scope",
        (project_scope or "").strip() or "_Not specified._",
        "",
        "## 2. Specific Requirements",
    ]

    for type_key, heading, prefix in _SRS_SECTIONS:
        lines += ["", f"### {heading}"]
        items = by_type.get(type_key) or []
        if not items:
            lines += ["", "_None captured._"]
            continue
        for i, r in enumerate(items, start=1):
            lines += ["", f"**{prefix}-{i}.** {(r.get('statement') or '').strip()}"]
            meta = _srs_meta(r)
            if meta:
                lines.append(f"_{meta}_")

    lines.append("")
    return "\n".join(lines)


def srs_to_text(md: str) -> str:
    """Strip the Markdown markers used by compile_srs for a plain-text export."""
    return md.replace("#", "").replace("*", "").replace("_", "").strip()


# Map common typographic characters to Latin-1-safe equivalents so the PDF renders
# with the built-in font (no embedded Unicode font needed, works in any environment).
_PDF_REPLACEMENTS = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", "·": "-", "•": "-",
}


def _pdf_safe(text: str) -> str:
    for bad, good in _PDF_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


def compile_srs_pdf(
    *,
    project_title: str,
    project_background: str | None = None,
    project_scope: str | None = None,
    requirements: Iterable[dict],
) -> bytes:
    """Render the SRS as a paginated PDF (same structure as compile_srs).

    fpdf2 is imported lazily so the Markdown/text export paths never depend on it.
    """
    from fpdf import FPDF  # lazy import: only needed for PDF export
    from fpdf.enums import XPos, YPos

    class _SRSDoc(FPDF):
        def footer(self) -> None:
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 10, f"Page {self.page_no()}", align="C")

    by_type = _bucket_requirements(requirements)

    pdf = _SRSDoc(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_title(_pdf_safe(f"Software Requirements Specification - {project_title}"))
    pdf.add_page()

    def block(text: str, *, size: int, style: str = "", h: float = 6.0, top: float = 0.0,
              gray: int | None = None, indent: float = 0.0, markdown: bool = False) -> None:
        # Always return the cursor to the left margin so the next full-width block
        # has the page's full text width available.
        if top:
            pdf.ln(top)
        pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(gray, gray, gray) if gray is not None else pdf.set_text_color(0, 0, 0)
        if indent:
            pdf.set_x(pdf.l_margin + indent)
        pdf.multi_cell(0, h, _pdf_safe(text), markdown=markdown,
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(0, 0, 0)

    # Title block
    block("Software Requirements Specification", size=18, style="B", h=9)
    block(project_title, size=13, h=7, gray=90)

    block("1. Introduction", size=14, style="B", h=7, top=3)
    block("1.1 Purpose", size=11, style="B", h=6, top=1)
    block(
        f"This document specifies the software requirements for {project_title}, "
        "compiled from AI-assisted stakeholder interviews.",
        size=11, h=6,
    )
    block("1.2 Background", size=11, style="B", h=6, top=1)
    block((project_background or "").strip() or "Not specified.", size=11, h=6)
    block("1.3 Scope", size=11, style="B", h=6, top=1)
    block((project_scope or "").strip() or "Not specified.", size=11, h=6)

    block("2. Specific Requirements", size=14, style="B", h=7, top=4)
    for type_key, title, prefix in _SRS_SECTIONS:
        block(title, size=11, style="B", h=6, top=2)
        items = by_type.get(type_key) or []
        if not items:
            block("None captured.", size=10, style="I", h=6, gray=120)
            continue
        for i, r in enumerate(items, start=1):
            statement = (r.get("statement") or "").strip()
            # markdown=True bolds the **FR-1.** id while leaving the statement regular
            block(f"**{prefix}-{i}.** {statement}", size=11, h=6, markdown=True)
            meta = _srs_meta(r)
            if meta:
                block(meta, size=9, style="I", h=5, gray=110, indent=4)
            pdf.ln(1)

    return bytes(pdf.output())
