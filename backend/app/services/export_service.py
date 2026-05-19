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
