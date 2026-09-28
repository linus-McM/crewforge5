"""R-S5: `crew survey|validate|status` over .claude/crews/<lang>.json, and the crew gate on `build accept`."""

import json
from pathlib import Path

import pytest

from conftest import PLAN_BODY, fill
from crewforge5 import crew, init
from crewforge5 import project as p


def manifest(repo: Path, lang: str = "python", **over) -> Path:
    data = {
        "language": lang,
        "stack_profile": f".claude/crews/{lang}.profile.md",
        "commands": {"test": "pytest"},
        "crew": {"developer": f"{lang}-developer", "tester": f"{lang}-tester"},
        "validation": {f"{lang}-developer": "A", f"{lang}-tester": "A"},
        "generated": [f"{lang}-developer", f"{lang}-tester"],
        "reused": [],
        **over,
    }
    path = repo / crew.CREWS / f"{lang}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def scripts(monkeypatch):
    """Stub the gate scripts: detect_language.sh, crew_check.sh, the agent validator and grade.sh."""
    answers = {"detect": "STATUS=OK\nLANG=python\n", "check": "STATUS=CACHED\nSTALE=false\nWORKTREE_AGENTS=ok\n", "fails": 0, "calls": []}

    def fake(root: Path, rel: str, *args: str) -> dict:
        answers["calls"].append((rel, args))
        if rel.endswith("detect_language.sh"):
            out = answers["detect"]
        elif rel.endswith("crew_check.sh"):
            out = answers["check"]
        elif rel == init.VALIDATORS["agent"]:
            out = '[\n{"status":"FAIL","check":"x","detail":"y"}\n]\n' if answers["fails"] else "[]\n"
        elif rel == init.GRADE:
            out = "grade=C\nfails=1\n" if answers["fails"] else "grade=A\nfails=0\n"
        else:
            raise AssertionError(rel)
        return {"exit": 0, "stdout": out, "stderr": ""}

    monkeypatch.setattr(p, "script", fake)
    return answers


def test_status_without_crews_points_at_survey(run):
    assert run("crew", "status") == {"ok": True, "crews": [], "next": "/crewforge5:crew survey", "stage": "crew"}


def test_status_reports_roles_and_grades(run, repo):
    manifest(repo)
    out = run("crew", "status")
    (crew_,) = out["crews"]
    assert crew_["language"] == "python" and crew_["passing"] is True and crew_["problems"] == []
    assert crew_["grades"] == {"python-developer": "A", "python-tester": "A"} and crew_["roles"]["tester"] == "python-tester"
    assert out["next"] == "nothing to do: every crew passes"


def test_status_flags_a_failing_or_missing_grade(run, repo):
    manifest(repo, "go", validation={"go-developer": "B"})
    manifest(repo, "python")
    out = run("crew", "status")
    go = next(c for c in out["crews"] if c["language"] == "go")
    assert go["passing"] is False and go["problems"] == ["go-tester has no validation grade", "go-developer graded B"]
    assert out["next"] == "/crewforge5:crew forge go"
    assert [c["language"] for c in run("crew", "status", "python")["crews"]] == ["python"]


def test_status_of_an_unknown_language(run):
    (crew_,) = run("crew", "status", "rust")["crews"]
    assert crew_["exists"] is False and crew_["passing"] is False


def test_status_reports_a_malformed_manifest(run, repo):
    path = manifest(repo)
    data = json.loads(path.read_text())
    del data["validation"]
    path.write_text(json.dumps(data))
    (crew_,) = run("crew", "status")["crews"]
    assert "manifest missing `validation`" in crew_["problems"] and "no validation grades recorded" in crew_["problems"]


def test_survey_detects_the_language_and_asks_for_a_profile(run, scripts):
    out = run("crew", "survey")
    assert out["ok"] and out["language"] == "python" and out["status"] == "OK"
    assert "stack-surveyor" in out["next"] and ".claude/crews/python.profile.md" in out["next"]


def test_survey_with_a_profile_points_at_forge(run, repo, scripts):
    (repo / crew.CREWS).mkdir(parents=True)
    (repo / crew.CREWS / "python.profile.md").write_text("profile\n")
    out = run("crew", "survey")
    assert out["profile"] == ".claude/crews/python.profile.md" and out["next"] == "/crewforge5:crew forge python"


def test_survey_on_an_ambiguous_repo_asks_the_user(run, scripts):
    scripts["detect"] = "STATUS=AMBIGUOUS\nCANDIDATES=python,typescript\n"
    out = run("crew", "survey")
    assert out["language"] is None and out["candidates"] == ["python", "typescript"] and "[project] language" in out["next"]


def test_configured_language_wins_over_detection(run, toml_config, scripts):
    toml_config(project={"language": "bash"})
    out = run("crew", "survey")
    assert out["language"] == "bash" and out["status"] == "CONFIGURED"
    assert not scripts["calls"]


def test_validate_passes_a_cached_crew_with_passing_grades(run, repo, scripts):
    manifest(repo)
    (repo / crew.AGENTS).mkdir(parents=True)
    for name in ("python-developer", "python-tester"):
        (repo / crew.AGENTS / f"{name}.md").write_text("---\nname: x\n---\n")
    out = run("crew", "validate", "python")
    assert out["ok"] and out["measured"] == {"python-developer": "A", "python-tester": "A"} and out["worktree_agents"] == "ok"
    assert ("skills/team-sprint/scripts/crew_check.sh", ("check", "python", "--project-dir", str(repo))) in scripts["calls"]


def test_validate_refuses_a_rebuild_verdict_or_a_regraded_agent(run, repo, scripts):
    manifest(repo)
    scripts["check"] = "STATUS=REBUILD\nREASON=unresolved:python-tester\n"
    out = run("crew", "validate")
    assert out["ok"] is False and "REBUILD unresolved:python-tester" in out["reason"] and out["next"] == "/crewforge5:crew forge python"
    scripts["check"] = "STATUS=CACHED\n"
    scripts["fails"] = 1
    (repo / crew.AGENTS).mkdir(parents=True)
    (repo / crew.AGENTS / "python-developer.md").write_text("x\n")
    out = run("crew", "validate", "python")
    assert out["ok"] is False and "python-developer now grades C" in out["problems"]


def test_validate_without_a_detectable_language(run, scripts):
    scripts["detect"] = "STATUS=UNKNOWN\n"
    out = run("crew", "validate")
    assert out["ok"] is False and "cannot tell the project language" in out["reason"]


# --- the build accept gate (off by default) -------------------------------------


@pytest.fixture
def filled_plan(run, repo, accepted_spec) -> Path:
    run("build", "new")
    fill(repo / "crewforge5/feat/plan.md", **PLAN_BODY)
    return repo / "crewforge5/feat/plan.md"


def test_require_crew_is_off_by_default(run, filled_plan, scripts):
    assert p.config(filled_plan.parents[2])["build"]["require_crew"] is False
    assert run("build", "accept")["ok"]
    assert not scripts["calls"], "no language detection unless the gate is on"


def test_build_accept_refuses_without_a_passing_crew(run, repo, filled_plan, toml_config, scripts):
    toml_config(build={"require_crew": True}, project={"language": "python"})
    out = run("build", "accept")
    assert out["ok"] is False and "no python crew with passing validation grades" in out["reason"]
    assert out["next"] == "/crewforge5:crew forge python"
    assert "Status: draft" in filled_plan.read_text()
    manifest(repo, validation={"python-developer": "A", "python-tester": "C"})
    assert run("build", "accept")["next"] == "/crewforge5:crew forge python"
    manifest(repo)
    assert run("build", "accept")["ok"]


def test_build_accept_detects_the_language_when_none_is_configured(run, repo, filled_plan, toml_config, scripts):
    toml_config(build={"require_crew": True})
    scripts["detect"] = "STATUS=OK\nLANG=go\n"
    assert run("build", "accept")["next"] == "/crewforge5:crew forge go"
    manifest(repo, "go")
    assert run("build", "accept")["ok"]


def test_build_accept_reports_plan_problems_before_the_crew(run, accepted_spec, toml_config, scripts):
    run("build", "new")
    toml_config(build={"require_crew": True}, project={"language": "python"})
    out = run("build", "accept")
    assert out["ok"] is False and "unfilled section" in out["reason"]


# --- R-C1: [commands] absorbs the manifest's command section ---


def test_validate_adopts_the_crew_commands_into_the_config(run, repo, scripts):
    manifest(repo, commands={"test": "pytest -q", "lint": "ruff check .", "coverage": "pytest --cov"})
    out = run("crew", "validate", "python")
    assert out["ok"] and out["commands_adopted"] == {"test": "pytest -q", "lint": "ruff check ."}  # only keys [commands] has
    cfg = p.config(repo)["commands"]
    assert cfg["test"] == "pytest -q" and cfg["lint"] == "ruff check ." and cfg["build"] == ""
    text = (repo / p.CONFIG_NAME).read_text()
    assert "# the project's test command" in text  # the template's comments survive
    assert p.config(repo)["hooks"]["enabled"] is True  # the rest of the file is intact


def test_validate_never_overrides_a_configured_command(run, repo, scripts, toml_config):
    toml_config(commands={"test": "make test"})
    manifest(repo)
    out = run("crew", "validate", "python")
    assert out["ok"] and out["commands_adopted"] == {}
    assert p.config(repo)["commands"]["test"] == "make test"
    assert out["next"] == "nothing to do: the crew passes"


def test_set_config_adds_a_missing_table_and_key(repo):
    (repo / p.CONFIG_NAME).write_text('[project]\nhome = "crewforge5"\n')
    p.set_config(repo, "commands", {"test": 'pytest -k "not slow"'})
    assert p.config(repo)["commands"]["test"] == 'pytest -k "not slow"'
    assert p.config(repo)["project"]["home"] == "crewforge5"
