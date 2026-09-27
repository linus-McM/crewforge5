"""R-S1, R-V5, R-W3: the stage commands are short, least-privilege, open with the preamble and fall back inline."""

import re
from pathlib import Path

import pytest

from crewforge5 import workflows
from crewforge5.project import PLUGIN_ROOT, TEMPLATES

COMMANDS = PLUGIN_ROOT / "commands"
STAGES = ["plan", "design", "build"]
MAX_LINES = 40
ALLOWED = {"Bash(uv run *)", "Bash(git *)", "Read", "Edit", "Write", "Glob", "Grep", "AskUserQuestion", "Agent", "Workflow", "Skill"}


def frontmatter(path: Path) -> dict[str, str]:
    found = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.DOTALL)
    assert found, f"{path.name} has no frontmatter"
    return dict(line.split(": ", 1) for line in found.group(1).splitlines() if ": " in line)


@pytest.mark.parametrize("path", sorted(COMMANDS.glob("*.md")), ids=lambda p: p.stem)
def test_every_command_is_short_and_described(path: Path):
    assert len(path.read_text().splitlines()) <= MAX_LINES, f"{path.name} is over {MAX_LINES} lines"
    fm = frontmatter(path)
    assert fm.get("description") and fm.get("argument-hint")


@pytest.mark.parametrize("stage", STAGES)
def test_stage_command_frontmatter_is_least_privilege(stage):
    fm = frontmatter(COMMANDS / f"{stage}.md")
    tools = [t.strip() for t in fm["allowed-tools"].split(",")]
    assert set(tools) <= ALLOWED, f"not on the allow list: {set(tools) - ALLOWED}"
    assert "Bash" not in tools, "bare Bash is not least privilege"
    assert "Bash(uv run *)" in tools and "AskUserQuestion" in tools and "Workflow" in tools
    for action in ("new", "check", "accept", "status"):
        assert action in fm["argument-hint"]


@pytest.mark.parametrize("stage", STAGES)
def test_stage_command_opens_with_the_preamble(stage):
    body = (COMMANDS / f"{stage}.md").read_text().split("\n---\n", 1)[1]
    assert body.startswith((TEMPLATES / "command-preamble.md").read_text().strip())
    for action in ("new", "check", "accept", "status"):
        assert re.search(rf"^## {action}\b", body, re.MULTILINE), f"{stage}.md has no `## {action}` section"


@pytest.mark.parametrize("stage", STAGES)
def test_every_workflow_step_has_an_inline_fallback(stage):
    text = (COMMANDS / f"{stage}.md").read_text()
    name = f"crewforge5:{workflows.CATALOG[stage]}"
    steps = [line for line in text.splitlines() if name in line]
    assert steps, f"{stage}.md never runs {name}"
    assert all("Inline fallback:" in line for line in steps)


@pytest.mark.parametrize("stage", STAGES)
def test_only_a_human_accepts(stage):
    accept = (COMMANDS / f"{stage}.md").read_text().split("## accept", 1)[1].split("\n## ", 1)[0]
    assert "Only a human accepts" in accept and "AskUserQuestion" in accept
    assert accept.index("AskUserQuestion") < accept.index(f"crewforge5 {stage} accept")


def test_stage_commands_hand_on_in_pipeline_order():
    assert "/crewforge5:design new" in (COMMANDS / "plan.md").read_text()
    assert "/crewforge5:build new" in (COMMANDS / "design.md").read_text()


def test_plan_new_folds_in_the_divergent_and_grilling_interview():
    new = (COMMANDS / "plan.md").read_text().split('## new "<title>"', 1)[1].split("\n## ", 1)[0]
    assert "Diverge" in new and "Grill" in new and "one question at a time" in new


def test_design_new_carries_concerns_and_the_requirements_trace():
    new = (COMMANDS / "design.md").read_text().split("## new", 1)[1].split("\n## ", 1)[0]
    assert "tech-debt audit" in new and "disposition" in new and "trace" in new


def test_build_new_runs_in_plan_mode_with_test_first_steps():
    new = (COMMANDS / "build.md").read_text().split("## new", 1)[1].split("\n## ", 1)[0]
    assert "plan mode" in new and "failing test" in new


def section(stage: str, heading: str) -> str:
    return (COMMANDS / f"{stage}.md").read_text().split(f"\n## {heading}", 1)[1].split("\n## ", 1)[0]


def test_build_implements_red_green_per_step_then_simplifies():
    """R-T1, R-T3, R-T6: red then green per step, sync, a per-step commit, /simplify then sync at the end."""
    implement = section("build", "implement")
    order = [implement.index(s) for s in ("build red <n>", "build green <n>", "build sync", "build(<slug>): <step>", "/simplify")]
    assert order == sorted(order)
    assert "build sync` once more" in implement.split("/simplify", 1)[1]


def test_build_runs_the_story_executor_with_an_inline_fallback():
    """R-W2, R-W3: the parallel path is the story-executor workflow; the command applies each branch and runs the gate."""
    implement = section("build", "implement")
    line = next(line for line in implement.splitlines() if f"crewforge5:{workflows.CATALOG['implement']}" in line)
    assert "Inline fallback:" in line and "cherry-pick -n <test_commit>" in line
    assert line.index("<test_commit>") < line.index("build red <n>") < line.index("-n <commit>") < line.index("build green <n>")


def test_build_fix_mode_locks_tests():
    fix = section("build", "fix on | fix off")
    assert "crewforge5 build fix on" in fix and "denies edits to test files" in fix and "crewforge5 build fix off" in fix
    for action in ("implement", "red", "green", "sync", "fix on|off"):
        assert action in frontmatter(COMMANDS / "build.md")["argument-hint"]


def test_execute_takes_an_accepted_feature_plan():
    """R-S7 adapter: `next` after `build accept` is /crewforge5:execute, which runs build implement on plan.md."""
    skill = (PLUGIN_ROOT / "skills/execute/SKILL.md").read_text()
    alias = skill.split("## An accepted `crewforge5/<slug>/plan.md`", 1)[1].split("\n## ", 1)[0]
    assert "/crewforge5:build implement --slug <slug>" in alias and "accepted" in alias and "crewforge5:story-executor" in alias
