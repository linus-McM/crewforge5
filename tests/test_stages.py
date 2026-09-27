"""The plan -> design -> build lifecycle (R-S3, R-A1, R-A2) and status (R-S6)."""

from pathlib import Path

import pytest

from conftest import INTENT_BODY, PLAN_BODY, fill
from crewforge5 import artifacts

FEAT = Path("crewforge5/feat")


def test_plan_new_creates_intent_from_template(run, repo):
    out = run("plan", "new", "Claims status self-service")
    path = repo / "crewforge5/claims-status-self-service/intent.md"
    assert out["ok"] and out["slug"] == "claims-status-self-service" and out["path"] == str(path)
    text = path.read_text()
    assert text.startswith("# Intent: Claims status self-service\nAuthor: t. Status: draft. Risk: low.")
    for heading in artifacts.REQUIRED["intent.md"]:
        assert f"## {heading}" in text


@pytest.mark.parametrize("artifact", ["intent.md", "spec.md", "plan.md"])
def test_templates_carry_status_and_risk_metadata(artifact):
    from crewforge5 import project as p

    text = (p.TEMPLATES / artifact).read_text()
    assert "Status: draft." in text and "Risk: {risk}." in text
    assert "Risk: high" in (p.TEMPLATES / "intent.md").read_text()  # the high-risk triggers are named


def test_plan_new_refuses_a_duplicate_and_an_empty_title(run):
    run("plan", "new", "Dup")
    assert run("plan", "new", "Dup")["ok"] is False
    assert run("plan", "new")["ok"] is False
    assert run("plan", "new", "  !! ")["ok"] is False


def test_check_lists_every_unfilled_section_then_passes(run, repo):
    run("plan", "new", "Feat")
    out = run("plan", "check")
    assert out["ok"] is False and len(out["problems"]) == len(artifacts.REQUIRED["intent.md"])
    fill(repo / FEAT / "intent.md", **INTENT_BODY)
    out = run("plan", "check")
    assert out["ok"] is True and out["next"] == "/crewforge5:plan accept --slug feat"


def test_check_validates_the_metadata(run, repo):
    run("plan", "new", "Feat")
    path = repo / FEAT / "intent.md"
    fill(path, **INTENT_BODY)
    path.write_text(path.read_text().replace("Risk: low", "Risk: extreme"))
    out = run("plan", "check")
    assert out["ok"] is False and "invalid Risk: extreme" in out["reason"]


def test_accept_sets_status_and_names_the_next_stage(run, repo):
    run("plan", "new", "Feat")
    assert run("plan", "accept")["ok"] is False  # unfilled
    fill(repo / FEAT / "intent.md", **INTENT_BODY)
    out = run("plan", "accept")
    assert out["ok"] and out["status"] == "accepted" and out["next"] == "/crewforge5:design new --slug feat"
    assert "Status: accepted." in (repo / FEAT / "intent.md").read_text()


@pytest.mark.parametrize(("stage", "before"), [("design", "intent.md"), ("build", "spec.md")])
def test_each_new_is_refused_until_the_previous_artifact_is_accepted(run, repo, stage, before):
    run("plan", "new", "Feat")
    if stage == "build":
        fill(repo / FEAT / "intent.md", **INTENT_BODY)
        run("plan", "accept")
        out = run("build", "new")
        assert out["ok"] is False and "spec.md missing" in out["reason"]
        run("design", "new")
    out = run(stage, "new")
    assert out["ok"] is False and before in out["reason"] and "not accepted" in out["reason"]
    assert out["next"].endswith("accept --slug feat")
    for action in ("check", "accept"):
        assert run(stage, action)["ok"] is False


def test_the_full_walk_accepts_each_artifact(run, repo, accepted_plan):
    for name in ("intent.md", "spec.md", "plan.md"):
        assert artifacts.status((repo / FEAT / name).read_text()) == "accepted"


def test_later_artifacts_inherit_title_and_risk(run, repo):
    run("plan", "new", "Feat")
    path = repo / FEAT / "intent.md"
    fill(path, **INTENT_BODY)
    path.write_text(path.read_text().replace("Risk: low", "Risk: high", 1))
    run("plan", "accept")
    run("design", "new")
    spec = (repo / FEAT / "spec.md").read_text()
    assert spec.startswith("# Spec: Feat\n") and "Risk: high." in spec


def test_new_never_overwrites_an_existing_artifact(run, repo, accepted_intent):
    run("design", "new")
    fill(repo / FEAT / "spec.md", Requirements="kept")
    out = run("design", "new")
    assert out["ok"] is False and "already exists" in out["reason"]
    assert "kept" in (repo / FEAT / "spec.md").read_text()


def test_build_check_requires_the_adversarial_stamp_when_configured(run, repo, accepted_spec, toml_config):
    run("build", "new")
    plan = repo / FEAT / "plan.md"
    fill(plan, **PLAN_BODY)
    assert run("build", "check")["ok"] is True  # default: not required
    toml_config(build={"require_adversarial_stamp": True})
    out = run("build", "check")
    assert out["ok"] is False and "adversarial-review stamp" in out["reason"]
    plan.write_text(plan.read_text() + "\n<!-- adversarial-review: status=clean rounds=1 date=2026-09-27 reviewer=team-sprint-planner -->\n")
    assert run("build", "check")["ok"] is True
    out = run("build", "accept")
    assert out["ok"] and out["next"] == "/crewforge5:execute"


def test_status_with_no_features(run):
    out = run("status")
    assert out == {"ok": True, "features": [], "next": '/crewforge5:plan new "<title>"', "stage": "status"}


def test_status_lists_every_feature_and_one_next_command(run, repo, accepted_intent):
    run("plan", "new", "Other")
    out = run("status")
    assert out["ok"] and [f["slug"] for f in out["features"]] == ["feat", "other"]
    feat = next(f for f in out["features"] if f["slug"] == "feat")
    assert feat["artifacts"] == {"intent.md": "accepted", "spec.md": "missing", "plan.md": "missing"}
    assert feat["next"] == "/crewforge5:design new --slug feat"
    assert out["latest"] == "other" and out["next"] == "/crewforge5:plan check --slug other"


def test_status_for_one_slug(run, repo, accepted_spec):
    run("build", "new")
    out = run("status", "--slug", "feat")
    assert out["artifacts"] == {"intent.md": "accepted", "spec.md": "accepted", "plan.md": "draft"}
    assert out["next"] == "/crewforge5:build check --slug feat"


def test_status_after_the_plan_is_accepted_points_at_execute(run, accepted_plan):
    assert run("status", "--slug", "feat")["next"] == "/crewforge5:execute"


def test_status_for_an_unknown_slug_is_a_refusal(run):
    out = run("status", "--slug", "ghost")
    assert out["ok"] is False and "ghost" in out["reason"]


def draft_plan(run, repo, **overrides) -> Path:
    run("build", "new")
    path = repo / FEAT / "plan.md"
    fill(path, **{**PLAN_BODY, **overrides})
    return path


def test_build_check_refuses_a_step_that_names_no_failing_test(run, repo, accepted_spec):
    draft_plan(run, repo, **{"Order of work": "1. write test_feat, it fails first\n2. implement feat"})
    out = run("build", "check")
    assert out["ok"] is False and "step 2 names no failing test" in out["reason"]


def test_build_check_refuses_an_order_of_work_without_numbered_steps(run, repo, accepted_spec):
    draft_plan(run, repo, **{"Order of work": "just do it, test later"})
    out = run("build", "check")
    assert out["ok"] is False and "no numbered steps" in out["reason"]


def test_high_risk_plan_needs_a_named_tech_lead(run, repo, accepted_spec):
    path = draft_plan(run, repo)
    path.write_text(artifacts.set_meta(path.read_text(), "Risk", "high"))
    out = run("build", "check")
    assert out["ok"] is False and "Tech lead: <name>" in out["reason"]
    fill(path, Risks="- Tech lead: Dana\n- the migration is the riskiest step")
    assert run("build", "check")["ok"]


def test_unknown_feature_points_at_a_command_that_exists(run):
    out = run("status", "--slug", "nope")
    assert out["ok"] is False and out["next"] == "/crewforge5:plan status"
