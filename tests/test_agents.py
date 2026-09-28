"""R-P1, R-P2, R-G6: every plugin agent declares its frontmatter; reviewer and verifier are lean and read-only."""

import re
from pathlib import Path

import pytest

from crewforge5.project import PLUGIN_ROOT

AGENTS = sorted((PLUGIN_ROOT / "agents").glob("*.md"))
HOOK_LINE = "If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook."
READ_ONLY = {"Bash", "Read", "Grep", "Glob"}


def frontmatter(path: Path) -> dict[str, str]:
    found = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.DOTALL)
    assert found, f"{path.name} has no frontmatter"
    return dict(line.split(": ", 1) for line in found.group(1).splitlines() if ": " in line)


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.stem)
def test_every_agent_declares_its_keys_and_the_hook_line(path: Path):
    fm = frontmatter(path)
    assert all(fm.get(key) for key in ("name", "description", "tools", "model"))
    assert fm["name"] == path.stem and not {"hooks", "permissionMode"} & set(fm)
    assert HOOK_LINE in path.read_text()


@pytest.mark.parametrize(("name", "model"), [("reviewer", "opus"), ("verifier", "sonnet")])
def test_reviewer_and_verifier_are_read_only(name: str, model: str):
    path = PLUGIN_ROOT / "agents" / f"{name}.md"
    fm = frontmatter(path)
    assert fm["model"] == model
    assert {t.strip() for t in fm["tools"].split(",")} <= READ_ONLY, "no Edit, Write or Agent"
    assert "Do not edit any file" in path.read_text()
    assert len(path.read_text().splitlines()) <= 20, "lean: the passes live in REVIEW.md and the review workflow"


def test_the_reviewer_carries_the_three_passes_and_both_lenses():
    text = (PLUGIN_ROOT / "agents/reviewer.md").read_text()
    for heading in ("## Bugs", "## Security", "## Compliance"):
        assert heading in text
    assert "Architecture lens" in text and "Boundary lens" in text and "Important:" in text and "Nit:" in text
