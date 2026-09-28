"""Interop with cc_sdlc: `build new --from-sdlc` (R-X1) and formats pinned to cc_sdlc's templates (R-X2)."""

import json
import shutil
from pathlib import Path

import pytest

from conftest import PLAN_BODY, fill
from crewforge5 import artifacts, interop, review, tdd
from crewforge5 import project as p

FIXTURES = Path(__file__).parent / "fixtures/cc_sdlc"
FORMATS = json.loads((FIXTURES / "formats.json").read_text())  # vendored from cc_sdlc; re-vendor deliberately
SLUG = "claims-status"


@pytest.fixture
def sdlc_feature(repo: Path) -> Path:
    """cc_sdlc's accepted claims-status feature (intent.md and spec.md) under the project's `sdlc/`."""
    shutil.copytree(FIXTURES / "sdlc", repo / "sdlc")
    return repo / "sdlc" / SLUG


# --- R-X1 -------------------------------------------------------------------------------------------------------


def test_from_sdlc_imports_the_accepted_spec_and_writes_plan(run, repo, sdlc_feature):
    out = run("build", "new", "--from-sdlc", SLUG)
    assert out["ok"], out
    feature = repo / "crewforge5" / SLUG
    assert out["slug"] == SLUG and out["path"] == str(feature / "plan.md")
    assert out["from_sdlc"] == f"sdlc/{SLUG}/spec.md"
    spec = (feature / "spec.md").read_text()
    assert f"From: sdlc/{SLUG}/spec.md (accepted). Status: accepted. Risk: medium." in spec
    assert artifacts.sections(spec) == artifacts.sections((sdlc_feature / "spec.md").read_text())
    intent = (feature / "intent.md").read_text()
    assert f"From: sdlc/{SLUG}/intent.md (accepted). Author: dana. Status: accepted." in intent
    plan = (feature / "plan.md").read_text()
    assert plan.startswith("# Plan: Claims status\n") and "Risk: medium." in plan
    assert run("status", "--slug", SLUG)["artifacts"] == {"intent.md": "accepted", "spec.md": "accepted", "plan.md": "draft"}


def test_the_imported_feature_runs_the_build_stage(run, repo, sdlc_feature):
    run("build", "new", "--from-sdlc", SLUG)
    fill(repo / "crewforge5" / SLUG / "plan.md", **PLAN_BODY)
    out = run("build", "accept", "--slug", SLUG)
    assert out["ok"] and out["status"] == "accepted", out


def test_refused_while_the_cc_sdlc_spec_is_a_draft(run, repo, sdlc_feature):
    spec = sdlc_feature / "spec.md"
    spec.write_text(spec.read_text().replace("Status: accepted", "Status: draft"))
    out = run("build", "new", "--from-sdlc", SLUG)
    assert out["ok"] is False and f"sdlc/{SLUG}/spec.md is not accepted" in out["reason"]
    assert out["next"] == "/sdlc:design accept"
    assert not (repo / "crewforge5" / SLUG).exists()  # nothing is written from a draft


def test_refused_while_the_cc_sdlc_intent_is_a_draft(run, repo, sdlc_feature):
    intent = sdlc_feature / "intent.md"
    intent.write_text(intent.read_text().replace("Status: accepted", "Status: draft"))
    out = run("build", "new", "--from-sdlc", SLUG)
    assert out["ok"] is False and "intent.md is not accepted" in out["reason"]
    assert not (repo / "crewforge5" / SLUG).exists()


def test_refused_without_the_cc_sdlc_feature(run, repo):
    out = run("build", "new", "--from-sdlc", "nope")
    assert out["ok"] is False and "sdlc/nope/spec.md missing" in out["reason"]


def test_refused_when_the_spec_drifted_from_the_shared_format(run, repo, sdlc_feature):
    spec = sdlc_feature / "spec.md"
    spec.write_text(spec.read_text().replace("## Concerns", "## Worries"))
    out = run("build", "new", "--from-sdlc", SLUG)
    assert out["ok"] is False and "missing section: Concerns" in out["reason"]


def test_never_overwrites_a_crewforge5_feature_of_the_same_name(run, repo, sdlc_feature):
    run("plan", "new", "Claims status")
    out = run("build", "new", "--from-sdlc", SLUG)
    assert out["ok"] is False and "was not imported from" in out["reason"]


def test_a_second_import_reuses_the_copy_and_refuses_the_duplicate_plan(run, repo, sdlc_feature):
    assert run("build", "new", "--from-sdlc", SLUG)["ok"]
    out = run("build", "new", "--from-sdlc", SLUG)
    assert out["ok"] is False and "plan.md already exists" in out["reason"]


def test_sdlc_home_follows_config_and_env(run, repo, sdlc_feature, toml_config, monkeypatch):
    shutil.move(repo / "sdlc", repo / "process")
    toml_config(interop={"sdlc_home": "process"})
    assert run("build", "new", "--from-sdlc", SLUG)["ok"]
    monkeypatch.setenv("SDLC_HOME", "../outside")
    assert "inside the project" in run("build", "new", "--from-sdlc", SLUG)["reason"]


def test_from_sdlc_is_only_for_build_new(run, repo, sdlc_feature):
    out = run("design", "new", "--from-sdlc", SLUG)
    assert out["ok"] is False and "build new only" in out["reason"]


def test_stamp_keeps_the_body_and_risk():
    text = (FIXTURES / "sdlc" / SLUG / "spec.md").read_text()
    stamped = interop.stamp(text, "sdlc/x/spec.md")
    assert stamped.splitlines()[1] == "From: sdlc/x/spec.md (accepted). Status: accepted. Risk: medium."
    assert stamped.splitlines()[2:] == text.splitlines()[2:]


# --- R-X2 -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("artifact", sorted(FORMATS["required"]))
def test_required_sections_match_cc_sdlc(artifact):
    assert artifacts.REQUIRED[artifact] == FORMATS["required"][artifact]


@pytest.mark.parametrize("artifact", sorted(FORMATS["templates"]))
def test_templates_match_cc_sdlc(artifact):
    lines = (p.TEMPLATES / artifact).read_text().splitlines()
    theirs = FORMATS["templates"][artifact]
    assert lines[0] == theirs["title"]
    assert lines[1] == theirs["metadata"]
    assert [line[3:] for line in lines if line.startswith("## ")] == theirs["sections"]


def test_artifact_names_match_cc_sdlc():
    from crewforge5 import stages

    names = set(stages.ARTIFACTS.values()) | {"review.md"}
    assert names == set(FORMATS["required"])
    assert tdd.LOG == "tdd.jsonl" and review.REPORT == "test-report.json"


def test_tdd_and_test_report_carry_cc_sdlc_keys(run, repo, accepted_plan, toml_config):
    for step in ("1", "2"):
        toml_config(commands={"test": "exit 1"})
        assert run("build", "red", step)["ok"]
        toml_config(commands={"test": "exit 0"})
        assert run("build", "green", step)["ok"]
    feature = repo / "crewforge5/feat"
    for entry in p.read_jsonl(feature / "tdd.jsonl"):
        assert set(FORMATS["tdd_entry_keys"]) <= set(entry)
    assert run("review", "run")["ok"]
    assert set(FORMATS["test_report_keys"]) <= set(p.read_json(feature / "test-report.json"))
