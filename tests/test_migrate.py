"""R-A1 / C1: `crewforge5 migrate` moves an old flow run or docs/plans plan into the feature home, once."""

import json
from pathlib import Path


def old_flow(repo: Path, flow: str = "execute", subject: str = "auth-sprint") -> Path:
    run_dir = repo / ".crewforge5" / flow / subject
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text('{"phase": {"0": {"status": "pass"}}}\n')
    (repo / ".crewforge5" / flow / "current").write_text(subject + "\n")
    return run_dir


def old_plan(repo: Path, name: str = "1-2-token-refresh") -> Path:
    plans = repo / "docs/plans"
    plans.mkdir(parents=True, exist_ok=True)
    plan = plans / f"{name}.md"
    plan.write_text("# Token refresh\n<!-- adversarial-review: status=clean rounds=1 -->\n")
    (plans / f"{name}-review").mkdir()
    (plans / f"{name}-review" / "round-1.md").write_text("clean\n")
    return plan


def test_nothing_to_migrate_is_ok(run):
    out = run("migrate")
    assert out["ok"] and out["migrated"] == [] and "nothing to migrate" in out["next"]


def test_a_flow_run_moves_into_the_feature_home(run, repo):
    old_flow(repo)
    out = run("migrate")
    assert out["ok"], out
    (moved,) = out["migrated"]
    assert moved == {"source": ".crewforge5/execute/auth-sprint", "slug": "auth-sprint", "to": ["crewforge5/auth-sprint/migrated/execute"]}
    assert (repo / "crewforge5/auth-sprint/migrated/execute/state.json").exists()
    assert not (repo / ".crewforge5").exists()  # the pointer and empty dirs go with it
    record = json.loads((repo / "crewforge5/auth-sprint/migrated/MIGRATED.json").read_text())
    assert record[0]["source"] == ".crewforge5/execute/auth-sprint"


def test_a_plan_moves_with_its_review_dir(run, repo):
    old_plan(repo)
    out = run("migrate", "docs/plans/1-2-token-refresh.md")
    assert out["ok"], out
    base = repo / "crewforge5/1-2-token-refresh/migrated"
    assert (base / "1-2-token-refresh.md").exists() and (base / "1-2-token-refresh-review/round-1.md").exists()
    assert not (repo / "docs/plans/1-2-token-refresh.md").exists()


def test_migrate_is_idempotent(run, repo):
    old_plan(repo)
    old_flow(repo)
    assert len(run("migrate")["migrated"]) == 2
    again = run("migrate")
    assert again["ok"] and again["migrated"] == []
    named = run("migrate", "docs/plans/1-2-token-refresh.md")
    assert named["ok"] and named["already"] == "1-2-token-refresh"


def test_migrate_refuses_to_overwrite(run, repo):
    old_plan(repo)
    old_flow(repo, subject="1-2-token-refresh")
    clash = repo / "crewforge5/1-2-token-refresh/migrated/1-2-token-refresh.md"
    clash.parent.mkdir(parents=True)
    clash.write_text("someone else's\n")
    out = run("migrate")
    assert out["ok"] is False and "refusing to overwrite" in out["reason"]
    assert clash.read_text() == "someone else's\n"
    # nothing moved, not even the run that had no clash
    assert (repo / "docs/plans/1-2-token-refresh.md").exists() and (repo / ".crewforge5/execute/1-2-token-refresh").exists()


def test_slug_renames_the_destination(run, repo):
    old_plan(repo)
    out = run("migrate", "docs/plans/1-2-token-refresh.md", "--slug", "token-refresh")
    assert out["ok"] and out["migrated"][0]["slug"] == "token-refresh"
    assert (repo / "crewforge5/token-refresh/migrated/1-2-token-refresh.md").exists()


def test_migrate_refuses_an_unknown_source(run, repo):
    (repo / "notes.md").write_text("x\n")
    out = run("migrate", "notes.md")
    assert out["ok"] is False and "neither" in out["reason"]
    missing = run("migrate", "docs/plans/nope.md")
    assert missing["ok"] is False and "never migrated" in missing["reason"]
