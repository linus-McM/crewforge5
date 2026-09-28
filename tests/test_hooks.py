"""R-G1-R-G3, R-G7: the Python guardrail hooks and their registration in hooks.json."""

import io
import json
import re
from pathlib import Path

import pytest

from crewforge5 import hooks
from crewforge5.project import PLUGIN_ROOT

HOOKS_JSON = json.loads((PLUGIN_ROOT / "hooks/hooks.json").read_text())


def edit(path) -> dict:
    return {"tool_name": "Edit", "tool_input": {"file_path": str(path)}}


def denied(out) -> bool:
    return out is not None and out["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.fixture(autouse=True)
def hooks_env(monkeypatch):
    monkeypatch.delenv("CREWFORGE5_HOOKS", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)


@pytest.fixture
def opted_in(repo: Path) -> Path:
    (repo / ".crewforge5.toml").write_text("")
    return repo


def test_hooks_are_inert_without_crewforge5_toml(run, repo, accepted_plan):
    (repo / ".crewforge5.toml").unlink()
    run("build", "fix", "on")
    assert hooks.pre_edit(edit(repo / "tests/test_feat.py"), repo) is None
    assert hooks.post_edit(edit(repo / "rogue.py"), repo) is None


def test_protected_paths_are_denied(opted_in, toml_config):
    toml_config(build={"protected_paths": ["src/gen/**", "LICENSE"]})
    out = hooks.pre_edit(edit(opted_in / "src/gen/a.py"), opted_in)
    assert denied(out) and "protected" in out["hookSpecificOutput"]["permissionDecisionReason"]
    assert denied(hooks.pre_edit(edit("LICENSE"), opted_in))  # a relative path is judged from the project root
    assert denied(hooks.pre_edit(edit(opted_in / "src/../src/gen/b.py"), opted_in))
    assert hooks.pre_edit(edit(opted_in / "src/app.py"), opted_in) is None


def test_paths_outside_the_project_are_not_ours(opted_in, toml_config):
    toml_config(build={"protected_paths": ["**"]})
    assert hooks.pre_edit(edit(opted_in.parent / "elsewhere.py"), opted_in) is None
    assert hooks.pre_edit(edit(opted_in / "../elsewhere.py"), opted_in) is None
    assert denied(hooks.pre_edit(edit(opted_in / "inside.py"), opted_in))


def test_a_symlink_is_judged_by_its_in_repo_name(opted_in, toml_config):
    toml_config(build={"protected_paths": ["linked.py"]})
    (opted_in.parent / "outside.py").write_text("x")
    (opted_in / "linked.py").symlink_to(opted_in.parent / "outside.py")
    assert denied(hooks.pre_edit(edit(opted_in / "linked.py"), opted_in))


def test_fix_mode_locks_test_files_only(run, repo, accepted_plan):
    test_file = repo / "tests/test_feat.py"
    assert hooks.pre_edit(edit(test_file), repo) is None
    run("build", "fix", "on")
    out = hooks.pre_edit(edit(test_file), repo)
    assert denied(out) and "fix mode is on" in out["hookSpecificOutput"]["permissionDecisionReason"]
    for other_test in ("pkg/foo_test.go", "web/a.spec.ts", "test_x.py", "scripts/tests/t.bats"):
        assert denied(hooks.pre_edit(edit(repo / other_test), repo)), other_test
    assert hooks.pre_edit(edit(repo / "src/feat.py"), repo) is None
    run("build", "fix", "off")
    assert hooks.pre_edit(edit(test_file), repo) is None


@pytest.mark.parametrize("switch", ["toml", "env"])
def test_the_hooks_off_switch(run, repo, accepted_plan, monkeypatch, switch):
    run("build", "fix", "on")
    if switch == "env":
        monkeypatch.setenv("CREWFORGE5_HOOKS", "off")
    else:
        config = repo / ".crewforge5.toml"
        config.write_text(config.read_text().replace("[hooks]\nenabled = true", "[hooks]\nenabled = false"))
    assert hooks.pre_edit(edit(repo / "tests/test_feat.py"), repo) is None
    assert hooks.post_edit(edit(repo / "rogue.py"), repo) is None


def test_post_edit_says_when_a_file_is_missing_from_the_plan(run, repo, accepted_plan):
    out = hooks.post_edit(edit(repo / "rogue.py"), repo)
    text = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "rogue.py" in text and "feat/plan.md" in text and "Files that change" in text
    assert hooks.post_edit(edit(repo / "src/feat.py"), repo) is None
    assert hooks.post_edit(edit(repo / "crewforge5/feat/plan.md"), repo) is None
    assert hooks.post_edit(edit(repo / ".crewforge5.toml"), repo) is None


def test_post_edit_is_quiet_before_the_plan_is_accepted(run, repo, accepted_spec):
    run("build", "new")
    assert hooks.post_edit(edit(repo / "rogue.py"), repo) is None


def test_main_reads_stdin_and_prints_the_decision(opted_in, toml_config, monkeypatch, capsys):
    toml_config(build={"protected_paths": ["frozen/**"]})
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({**edit(opted_in / "frozen/a.py"), "cwd": str(opted_in)})))
    assert hooks.main(["pre-edit"]) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_prefers_the_opted_in_project_dir(opted_in, toml_config, monkeypatch, capsys, tmp_path_factory):
    toml_config(build={"protected_paths": ["frozen/**"]})
    elsewhere = tmp_path_factory.mktemp("sub")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(opted_in))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({**edit(opted_in / "frozen/a.py"), "cwd": str(elsewhere)})))
    hooks.main(["pre-edit"])
    assert "deny" in capsys.readouterr().out


def test_main_fails_open_on_a_broken_config(opted_in, monkeypatch, capsys):
    (opted_in / ".crewforge5.toml").write_text("[build\n")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(edit(opted_in / "a.py"))))
    assert hooks.main(["pre-edit"], opted_in) == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "not valid TOML" in captured.err


def registered() -> list[tuple[str, str, dict]]:
    return [(event, group.get("matcher", ""), hook) for event, groups in HOOKS_JSON["hooks"].items() for group in groups for hook in group["hooks"]]


def test_edit_hooks_are_registered_for_every_edit_tool():
    for event, name in (("PreToolUse", "pre-edit"), ("PostToolUse", "post-edit")):
        (hook,) = [h for e, m, h in registered() if e == event and name in h["command"]]
        matcher = next(m for e, m, h in registered() if h is hook)
        assert set(matcher.split("|")) == {"Edit", "Write", "MultiEdit"}
        assert ".crewforge5.toml" in hook["command"] and "uv run --offline --no-project" in hook["command"]


def test_hooks_stay_fast_and_offline():
    """R-G7: at most 10 s per hook (session start may take 180 s and only checks); no installs, no network."""
    for event, _, hook in registered():
        assert hook["timeout"] <= (180 if event == "SessionStart" else 10), hook["command"]
        assert not re.search(r"\b(curl|wget|pip install|npm install|npx|brew install|apt-get)\b", hook["command"])


def test_no_hook_arms_on_the_retired_opt_in_variable():
    for script in (PLUGIN_ROOT / "hooks").glob("*.sh"):
        assert 'CREWFORGE5_HOOKS:-0}" = "1"' not in script.read_text(), script.name
