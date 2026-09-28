"""R-T1-R-T4: red/green TDD evidence in tdd.jsonl, plan sync since acceptance, fix mode, and `tdd.complete`."""

import json
from pathlib import Path

import pytest

from conftest import git
from crewforge5 import build, tdd

FEATURE = "crewforge5/feat"


def log(repo: Path) -> list[dict]:
    path = repo / FEATURE / "tdd.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.fixture
def tests_fail(toml_config):
    def _set(failing: bool) -> None:
        toml_config(commands={"test": "exit 1" if failing else "exit 0"})

    return _set


def test_implementation_waits_for_an_accepted_plan(run, accepted_spec, tests_fail):
    run("build", "new")
    tests_fail(True)
    for argv in (("red", "1"), ("green", "1"), ("sync",), ("fix", "on")):
        out = run("build", *argv)
        assert out["ok"] is False and "plan.md is not accepted" in out["reason"]
        assert out["next"] == "/crewforge5:build accept --slug feat"


def test_red_needs_a_configured_test_command(run, accepted_plan):
    out = run("build", "red", "1")
    assert out["ok"] is False and "[commands] test" in out["reason"]


def test_red_is_refused_while_tests_pass(run, repo, accepted_plan, tests_fail):
    tests_fail(False)
    out = run("build", "red", "1")
    assert out["ok"] is False and "tests passed" in out["reason"]
    assert log(repo) == []


def test_red_records_a_failing_run(run, repo, accepted_plan, tests_fail):
    tests_fail(True)
    out = run("build", "red", "1")
    assert out["ok"] and out["phase"] == "red" and out["step"] == "1"
    (entry,) = log(repo)
    assert set(entry) == {"step", "phase", "sha", "ts", "exit"}
    assert entry["step"] == "1" and entry["phase"] == "red" and entry["exit"] == 1
    assert entry["sha"] == git(repo, "rev-parse", "HEAD") and entry["ts"].endswith("Z")


def test_green_needs_a_red_first(run, repo, accepted_plan, tests_fail):
    tests_fail(False)
    out = run("build", "green", "1")
    assert out["ok"] is False and "no red run" in out["reason"] and out["next"] == "crewforge5 build red 1"


def test_green_is_refused_while_tests_fail(run, repo, accepted_plan, tests_fail):
    tests_fail(True)
    run("build", "red", "1")
    out = run("build", "green", "1")
    assert out["ok"] is False and "still failing" in out["reason"] and out["exit"] == 1
    assert [e["phase"] for e in log(repo)] == ["red"]


def test_green_after_red_closes_a_cycle(run, repo, accepted_plan, tests_fail):
    tests_fail(True)
    run("build", "red", "step-1")
    tests_fail(False)
    out = run("build", "green", "step1")
    assert out["ok"] and out["cycles"] == 1
    assert [(e["step"], e["phase"], e["exit"]) for e in log(repo)] == [("1", "red", 1), ("1", "green", 0)]


def test_a_step_must_be_in_the_plan(run, accepted_plan, tests_fail):
    tests_fail(True)
    out = run("build", "red", "7")
    assert out["ok"] is False and "no Order-of-work step" in out["reason"] and out["steps"] == ["1", "2"]


def test_complete_needs_a_red_green_pair_for_every_step(run, repo, accepted_plan, tests_fail):
    feature = repo / FEATURE
    assert tdd.complete(feature) == {"complete": False, "steps": ["1", "2"], "missing": ["1", "2"]}
    tests_fail(True)
    run("build", "red", "1")
    run("build", "red", "2")
    tests_fail(False)
    run("build", "green", "1")
    assert tdd.complete(feature)["missing"] == ["2"]
    with pytest.raises(tdd.p.Blocked, match="no red->green pair for step 2"):
        tdd.require(feature)
    run("build", "green", "2")
    assert tdd.complete(feature)["complete"] is True
    assert tdd.require(feature)["missing"] == []


def test_a_green_before_its_red_does_not_count():
    assert tdd.pairs([{"step": "1", "phase": "green"}, {"step": "1", "phase": "red"}]) == {}
    assert tdd.pairs([{"step": "1", "phase": "red"}, {"step": "2", "phase": "green"}]) == {}


def test_accept_records_the_base_commit(run, repo, accepted_plan):
    state = json.loads((repo / FEATURE / build.STATE).read_text())
    assert state["accepted_sha"] == git(repo, "rev-parse", "HEAD")


def test_sync_passes_with_only_planned_and_owned_changes(run, repo, accepted_plan):
    (repo / "src").mkdir()
    (repo / "src/feat.py").write_text("x\n")
    out = run("build", "sync")
    assert out["ok"] and out["changed"] == ["src/feat.py"] and out["unplanned"] == []


def test_sync_reports_unplanned_files_committed_or_not(run, repo, accepted_plan):
    (repo / "rogue.py").write_text("x\n")
    git(repo, "add", "rogue.py")
    git(repo, "commit", "-qm", "sneak it in")
    (repo / "README.md").write_text("changed\n")  # the first porcelain line starts with a space
    (repo / "loose.txt").write_text("x\n")
    out = run("build", "sync")
    assert out["ok"] is False and "missing from plan.md" in out["reason"]
    assert out["unplanned"] == ["README.md", "loose.txt", "rogue.py"]
    assert out["planned"] == ["src/feat.py", "tests/test_feat.py"]


def test_sync_accepts_a_file_once_the_plan_lists_it(run, repo, accepted_plan):
    (repo / "extra.py").write_text("x\n")
    assert run("build", "sync")["ok"] is False
    plan = repo / FEATURE / "plan.md"
    plan.write_text(plan.read_text().replace("- tests/test_feat.py (new)", "- tests/test_feat.py (new)\n- `extra.py`: helper"))
    assert run("build", "sync")["ok"] is True


def test_fix_mode_toggles_in_build_state(run, repo, accepted_plan):
    assert run("build", "fix", "on")["fix"] is True
    assert build.fix_on(repo)
    assert run("build", "fix", "off")["fix"] is False
    assert not build.fix_on(repo)
    assert run("build", "fix", "sideways")["ok"] is False


def test_generated_developers_and_testers_claim_a_step_only_through_red_green():
    """R-T5: the crew factory seeds a `## Done` contract that names both gates and the tdd.jsonl log."""
    factory = (build.p.PLUGIN_ROOT / "agents/crew-factory.md").read_text()
    done = factory.split("## Done", 1)[1].split("```", 1)[0]
    assert "crewforge5 build red <n>" in done and "crewforge5 build green <n>" in done and "tdd.jsonl" in done
    assert "developer and tester also carry this section verbatim" in factory
    assert "the developer and tester carry the `## Done` section" in factory.split("## Completion gate", 1)[1]
