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
# plan.md's Order of work: numbered steps, each naming the failing test written first (R-S2).
STEP = re.compile(r"^\s*(\d+)[.)]\s+(.*)$", re.MULTILINE)
# Risk: high plans name the tech lead who accepts them (R-A2).
TECH_LEAD = re.compile(r"^\s*(?:[-*]\s*)?Tech lead:\s*(?!<)\S", re.MULTILINE | re.IGNORECASE)
METADATA = ("Status", "Risk")
BULLET = re.compile(r"^(?:[-*]|\d+[.)])\s+")  # a list marker only, so `.gitignore` keeps its dot
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
        elif not filled(found[heading]):
            problems.append(f"unfilled section: {heading}")
    return problems


def filled(body: str) -> bool:
    return not all(PLACEHOLDER.match(line) for line in body.splitlines() or [""])


def plan_problems(md: str) -> list[str]:
    """plan.md rules beyond the sections: every step names its failing test; Risk: high names a tech lead."""
    found, problems = sections(md), []
    order = found.get("Order of work", "")
    if filled(order):
        steps = STEP.findall(order)
        if not steps:
            problems.append("Order of work has no numbered steps (`1. ...`)")
        if untested := [n for n, body in steps if "test" not in body.lower()]:
            problems.append(f"Order of work step {', '.join(untested)} names no failing test")
    if meta(md, "Risk") == "high" and not TECH_LEAD.search(found.get("Risks", "")):
        problems.append("Risk: high needs a `Tech lead: <name>` line under Risks; the tech lead accepts this plan")
    return problems


def steps(md: str) -> list[str]:
    """The Order-of-work step numbers, in plan order."""
    return [n for n, _ in STEP.findall(sections(md).get("Order of work", ""))]


def list_items(body: str) -> list[str]:
    """Paths from a bulleted or comma-separated section body: the first word of each item, `(new)` and backticks stripped."""
    items: list[str] = []
    for line in body.splitlines():
        if PLACEHOLDER.match(line):
            continue
        line = BULLET.sub("", re.sub(r"\([^)]*\)", "", line).replace("`", "").strip()).strip()
        items += [part.split()[0].rstrip(":") for part in line.split(",") if part.strip()]  # a path, then any prose
    return items


def glob_regex(pattern: str) -> re.Pattern:
    """gitignore-style: `**` spans directories, `*` stays in one segment, a bare name matches at any depth."""
    pattern = pattern.removeprefix("**/")
    body = re.escape(pattern).replace(r"\*\*/", "(?:.*/)?").replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
    prefix = "" if "/" in pattern else "(?:.*/)?"
    return re.compile(f"^{prefix}{body}$")


def matches(rel: str, globs: list[str]) -> bool:
    return any(glob_regex(g).match(rel) for g in globs)


def stamped(md: str) -> bool:
    return bool(STAMP.search(md))


def render(template: Path, **fields: str) -> str:
    return template.read_text().format(**fields)
