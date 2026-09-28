"""R-S1, R-V5, R-W3: the stage commands are short, least-privilege, open with the preamble and fall back inline."""

import re
from pathlib import Path

import pytest

from crewforge5 import workflows
from crewforge5.project import PLUGIN_ROOT, TEMPLATES

COMMANDS = PLUGIN_ROOT / "commands"
STAGES = ["init", "plan", "design", "build"]
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
    """R-S7 / D5: `next` after `build accept` is /crewforge5:execute, a command running build implement then review."""
    alias = section("execute", "run  (the default)")
    assert "crewforge5 status --slug <slug>" in alias and "accepted" in alias and "crewforge5:story-executor" in alias
    order = [alias.index(s) for s in ("crewforge5 status", "/crewforge5:build implement", "/crewforge5:review run", "/crewforge5:review review")]
    assert order == sorted(order), "R-S7: status, then build, then review run, then review review"
    assert "Print the underlying commands you ran" in alias
    assert "shortcut" in (COMMANDS / "execute.md").read_text()


def test_execute_teams_routes_to_the_hidden_team_sprint_path():
    """D3: `execute --teams` builds the story plan from the accepted plan.md and runs team-sprint in graph mode."""
    teams = section("execute", "--teams  (graph-mode Teams path; kept until measured, spec D3)")
    assert teams.index("crewforge5 status") < teams.index("plan_stories.sh") < teams.index("skills/team-sprint/SKILL.md")
    assert "scheduling: graph" in teams and "C4" in teams
    fm = frontmatter(COMMANDS / "execute.md")
    tools = [t.strip() for t in fm["allowed-tools"].split(",")]
    assert set(tools) <= ALLOWED | {"Bash(bash *)"} and "Bash" not in tools
    assert "--teams" in fm["argument-hint"]
    body = (COMMANDS / "execute.md").read_text().split("\n---\n", 1)[1]
    assert body.startswith((TEMPLATES / "command-preamble.md").read_text().strip())


def test_build_hands_on_to_review_run():
    assert "Next: `/crewforge5:review run`" in section("build", "implement")


def test_review_command_is_least_privilege_and_opens_with_the_preamble():
    """R-S1, R-V5 for /crewforge5:review: run | review | evals, no AskUserQuestion needed (no human accept)."""
    path = COMMANDS / "review.md"
    fm = frontmatter(path)
    tools = [t.strip() for t in fm["allowed-tools"].split(",")]
    assert set(tools) <= ALLOWED and "Bash" not in tools
    assert {"Bash(uv run *)", "Agent", "Workflow"} <= set(tools)
    for action in ("run", "review", "evals", "status"):
        assert action in fm["argument-hint"]
    body = path.read_text().split("\n---\n", 1)[1]
    assert body.startswith((TEMPLATES / "command-preamble.md").read_text().strip())
    for action in ("run", "review", "evals", "status"):
        assert re.search(rf"^## {action}\b", body, re.MULTILINE), f"review.md has no `## {action}` section"


def test_review_runs_the_verifier_then_the_workflow_with_a_reviewer_fallback():
    """R-T2, R-W2, R-W3, R-P1: run spawns the verifier; review runs crewforge5:review, else the reviewer agent."""
    run_ = section("review", "run")
    assert "crewforge5 review run" in run_ and "crewforge5:verifier" in run_ and "fresh context" in run_
    review = section("review", "review")
    steps = [line for line in review.splitlines() if re.search(r"(?<!/)crewforge5:review\b(?!er)", line)]
    assert steps and all("Inline fallback:" in line and "crewforge5:reviewer" in line for line in steps)
    assert "two skeptics" in review and "five nits" in review
    assert review.index("red→green") < review.index("crewforge5 review review")
    assert "review(<slug>): review — review.md" in review
    assert "claude -p" in section("review", "evals") and "agent-evals.yml" in section("review", "evals")


def test_init_new_measures_then_audits_read_only():
    """R-S4, R-W2: init new measures, runs config-audit (else the context-hygiene passes inline) and gates on check."""
    new = section("init", "new [<config root>]")
    assert "crewforge5 init new" in new and "crewforge5:config-audit" in new and "context-hygiene" in new
    assert new.index("crewforge5 init new") < new.index("crewforge5:config-audit") < new.index("crewforge5 init check")
    assert "read-only" in new


def test_init_accept_applies_only_the_approved_edits_and_checkpoints():
    accept = section("init", "accept")
    assert "multiSelect" in accept and "never apply one the human did not pick" in accept
    assert accept.index("AskUserQuestion") < accept.index("Apply exactly those") < accept.index("crewforge5 init accept")
    assert "retention_gate.sh" in accept and "init(<slug>): accept — audit.md" in accept


def test_crew_command_wraps_the_surveyor_and_the_factory():
    """R-S5: survey | forge <lang> | validate | status over the CLI and the two crew agents."""
    path = COMMANDS / "crew.md"
    fm = frontmatter(path)
    tools = [t.strip() for t in fm["allowed-tools"].split(",")]
    assert set(tools) <= ALLOWED and "Bash" not in tools and {"Bash(uv run *)", "Agent"} <= set(tools)
    for action in ("survey", "forge <lang>", "validate", "status"):
        assert action in fm["argument-hint"]
    body = path.read_text().split("\n---\n", 1)[1]
    assert body.startswith((TEMPLATES / "command-preamble.md").read_text().strip())
    for action in ("survey", "forge", "validate", "status"):
        assert re.search(rf"^## {action}\b", body, re.MULTILINE), f"crew.md has no `## {action}` section"
    assert "crewforge5 crew survey" in section("crew", "survey") and "crewforge5:stack-surveyor" in section("crew", "survey")
    forge = section("crew", "forge <lang>")
    assert forge.index("crewforge5:crew-factory") < forge.index("crewforge5 crew validate <lang>")
    assert "/crewforge5:crew forge <lang>" in section("crew", "validate [<lang>]")
    assert "require_crew" in section("crew", "status [<lang>]")
