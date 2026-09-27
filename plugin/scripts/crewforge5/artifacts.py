"""Markdown artifact helpers: intent.md, spec.md and plan.md share one shape (the cc_sdlc templates).

A document is a `# Kind: Title` line, a metadata line (`Author: x. Status: draft. Risk: low.`),
then `## Section` blocks. A section holding only `<placeholder>` text counts as unfilled.
"""

from __future__ import annotations

import re
from pathlib import Path

PLACEHOLDER = re.compile(r"^\s*<[^>]*>\s*$")
HEADING = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
# The planner's stamp (skills/team-sprint-planner/references/plan-contract.md), checked by `build check`.
STAMP = re.compile(r"^<!-- adversarial-review: status=(clean|user-override)\b", re.MULTILINE)

REQUIRED = {
    "intent.md": ["Problem", "Proposed outcome", "Affected users and systems", "Constraints", "Open questions"],
    "spec.md": ["Requirements", "Design", "Concerns", "Open questions", "Proof"],
    "plan.md": ["Files that change", "Order of work", "Risks", "Proof"],
}
METADATA = ("Status", "Risk")
STATUSES = ("draft", "accepted")
RISKS = ("low", "medium", "high")


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def title(md: str) -> str:
    """`# Intent: Claims status` -> `Claims status`."""
    return md.splitlines()[0].lstrip("# ").split(":", 1)[-1].strip() if md else ""


def sections(md: str) -> dict[str, str]:
    parts = HEADING.split(md)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def set_section(md: str, heading: str, body: str) -> str:
    pattern = re.compile(rf"(^## {re.escape(heading)}\s*\n)(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return pattern.sub(lambda m: f"{m.group(1)}{body.rstrip()}\n\n", md, count=1)


def meta(md: str, field: str) -> str | None:
    """A metadata value from the first occurrence of `Field: value`, lower-cased."""
    match = re.search(rf"\b{field}:\s*([A-Za-z-]+)", md)
    return match.group(1).lower() if match else None


def set_meta(md: str, field: str, value: str) -> str:
    return re.sub(rf"\b{field}:\s*[A-Za-z-]+", f"{field}: {value}", md, count=1)


def status(md: str) -> str | None:
    return meta(md, "Status")


def validate(md: str, required: list[str]) -> list[str]:
    """Problems with the document; empty when the metadata is valid and every required section is filled."""
    problems = []
    allowed = {"Status": STATUSES, "Risk": RISKS}
    for field in METADATA:
        value = meta(md, field)
        if value is None:
            problems.append(f"missing metadata: {field}:")
        elif value not in allowed[field]:
            problems.append(f"invalid {field}: {value} (one of {', '.join(allowed[field])})")
    found = sections(md)
    for heading in required:
        if heading not in found:
            problems.append(f"missing section: {heading}")
        elif all(PLACEHOLDER.match(line) for line in found[heading].splitlines() or [""]):
            problems.append(f"unfilled section: {heading}")
    return problems


def stamped(md: str) -> bool:
    return bool(STAMP.search(md))


def render(template: Path, **fields: str) -> str:
    return template.read_text().format(**fields)
