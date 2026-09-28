"""Spec phase 8: the flow driver and the hidden flow skills are gone (R-V3, R-V6, R-P1, R-P3, R-P4, R-G5, R-S7)."""

import json
import re
from pathlib import Path

import pytest

from crewforge5 import cli, tdd
from crewforge5.project import PLUGIN_ROOT

COMMANDS = PLUGIN_ROOT / "commands"
# R-P3: the know-how skills that remain, plus team-sprint as the hidden graph-mode Teams path (D3).
KEPT = {
    "graphify",
    "archify",
    "playwright-cli",
    "ac-validate",
    "token-slim",
    "context-hygiene",
    "skill-validator",
    "agent-validator",
    "skill-rectifier",
    "agent-rectifier",
    "self-improve",
    "plugin-forge",
    "team-sprint",
}
RETIRED = {
    "execute",
    "plan-legacy",
    "init-legacy",
    "team-feature",
    "team-sprint-planner",
    "master-plan",
    "adhd",
    "grill-me",
    "adversarial-review",
    "tech-debt-audit",
    "pre-commit-review-fleet",
    "sprint-watchdog",
    "use-repo-code",
    "claude-config",
}
# Spec C1: every retired 0.x name except `execute` (a real command) is kept for one
# minor release as a hidden command stub that points at its replacement; removed in 1.1.0.
STUBS = RETIRED - {"execute"}
STUB_POINTER = re.compile(r"use `/crewforge5:([a-z-]+)`")


def is_stub(path: Path) -> bool:
    return "disable-model-invocation: true" in path.read_text().split("\n---\n", 1)[0]


CALL = re.compile(r"`crewforge5 ([a-z]+)(?: ([a-z]+))?")


def test_no_phases_manifest_or_flow_driver_remains():
    """R-V3 / R-V6 / R-P4: no phases.json anywhere, so no empty "judgment" gate can exist; the driver is gone."""
    assert not list(PLUGIN_ROOT.rglob("phases.json"))
    assert not (PLUGIN_ROOT / "scripts/flow").exists()
    hits = [p for p in PLUGIN_ROOT.rglob("*") if p.is_file() and p.suffix in {".md", ".sh", ".py", ".js", ".json"} and "subskill_resolve" in p.read_text(errors="replace")]
    assert not hits, f"still naming the retired resolver: {hits}"


def test_the_skill_set_is_the_target():
    """R-P3: at most 14 skills, exactly the know-how set plus team-sprint; the flow skills are gone."""
    skills = {d.name for d in (PLUGIN_ROOT / "skills").iterdir() if (d / "SKILL.md").exists()}
    assert skills == KEPT and len(skills) <= 14
    assert not skills & RETIRED


def command_calls(path: Path) -> set[tuple[str, str | None]]:
    """Every `crewforge5 <stage> [<action>]` call a command file makes."""
    return {(stage, action) for stage, action in CALL.findall(path.read_text())}


def cli_key(stage: str, action: str | None) -> tuple[str, str | None]:
    """The CLI key a call names; a bare `crewforge5 <stage>` names the stage's first action."""
    if not action:
        return next((key for key in cli.COMMANDS if key[0] == stage), (stage, None))
    return (stage, action) if (stage, action) in cli.COMMANDS else (stage, None)


@pytest.mark.parametrize("path", sorted(COMMANDS.glob("*.md")), ids=lambda p: p.stem)
def test_every_cli_call_in_a_command_is_a_cli_action(path: Path):
    """R-V3: a gate a command names is an action the CLI dispatches, never prose."""
    for stage, action in command_calls(path):
        assert cli_key(stage, action) in cli.COMMANDS, f"{path.name}: `crewforge5 {stage} {action}` is not a CLI action"


@pytest.mark.parametrize("path", sorted(p for p in COMMANDS.glob("*.md") if p.stem != "rules-install" and not is_stub(p)), ids=lambda p: p.stem)
def test_every_command_action_is_gated_by_the_cli(path: Path):
    """R-V3: each `## <action>` section of a stage command runs at least one CLI action: no empty gates."""
    body = path.read_text().split("\n---\n", 1)[1]
    sections = re.split(r"^## ", body, flags=re.MULTILINE)[1:]
    assert sections, f"{path.name} has no action sections"
    for section in sections:
        heading = section.splitlines()[0]
        calls = {(s, a) for s, a in CALL.findall(section) if cli_key(s, a) in cli.COMMANDS}
        assert calls, f"{path.name}: `## {heading}` names no CLI action"


def test_retired_names_are_hidden_stubs_for_one_minor_release():
    """C1: exactly the retired names are stubs; each is hidden and names one real (non-stub) command."""
    stubs = {p.stem for p in COMMANDS.glob("*.md") if is_stub(p)}
    assert stubs == STUBS
    for name in sorted(stubs):
        text = (COMMANDS / f"{name}.md").read_text()
        targets = STUB_POINTER.findall(text)
        assert len(targets) == 1, f"{name}.md must point at exactly one command"
        target = COMMANDS / f"{targets[0]}.md"
        assert target.exists() and not is_stub(target), f"{name}.md points at /crewforge5:{targets[0]}, not a command"
        assert "1.1.0" in text and len(text.splitlines()) <= 6


def test_execute_is_a_command_not_a_skill():
    """R-S7 / D5: the alias is commands/execute.md; the flow skill is gone."""
    assert (COMMANDS / "execute.md").exists() and not (PLUGIN_ROOT / "skills/execute").exists()


def test_sprint_watchdog_agent_and_hook_are_retired():
    """R-P1 / R-G5: no sprint-watchdog agent, no TaskUpdate hook; learn-capture stays on PostToolUse(Bash)."""
    assert not (PLUGIN_ROOT / "agents/sprint-watchdog.md").exists()
    assert not (PLUGIN_ROOT / "hooks/sprint-watchdog-guard.sh").exists()
    hooks = json.loads((PLUGIN_ROOT / "hooks/hooks.json").read_text())["hooks"]
    matchers = {entry.get("matcher") for entries in hooks.values() for entry in entries}
    assert "TaskUpdate" not in matchers
    post_bash = [h["command"] for e in hooks["PostToolUse"] if e.get("matcher") == "Bash" for h in e["hooks"]]
    assert any("learn-capture.sh" in c for c in post_bash)


def test_fake_completion_is_refused_by_tdd_evidence(run, repo, accepted_plan, toml_config):
    """R-T5 / R-G5: what the watchdog guard caught (a step claimed done with no proof) is a tdd.require refusal."""
    feature = repo / "crewforge5/feat"
    toml_config(commands={"test": "exit 0"})
    # A step "completed" without a failing test first: green alone is refused, and review run stays shut.
    assert run("build", "green", "1")["ok"] is False
    out = run("review", "run")
    assert out["ok"] is False and "no red->green pair" in out["reason"]
    # A hand-written log line claiming green without its red does not count either.
    (feature / "tdd.jsonl").write_text(json.dumps({"step": "1", "phase": "green", "sha": "x", "ts": "t", "exit": 0}) + "\n")
    assert tdd.complete(feature)["missing"] == ["1", "2"]
    with pytest.raises(Exception, match="no red->green pair"):
        tdd.require(feature)
