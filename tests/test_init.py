"""R-S4: `init new|check|accept|status` over crewforge5/init-<date>/audit.md, with the measurement scripts stubbed."""

import json
import shutil
from pathlib import Path

import pytest

from conftest import fill, git
from crewforge5 import cli, init
from crewforge5 import project as p

FILLED = {"Findings": "- Important: CLAUDE.md — restates the obvious", "Proposed edits": "1. CLAUDE.md — drop line 3", "Retention": "none", "Open questions": "none"}


class Scripts:
    """A stand-in for `project.script`: baseline.py, the validators, grade.sh and retention_gate.sh."""

    def __init__(self):
        self.skills = {"tidy": {"desc_chars": 120, "body_chars": 400, "trigger_phrases": [], "headings": []}}
        self.fails: dict[str, int] = {}
        self.retention_exit = 0
        self.calls: list[str] = []

    def __call__(self, root: Path, rel: str, *args: str) -> dict:
        self.calls.append(rel)
        if rel == init.BASELINE:
            return {"exit": 0, "stdout": json.dumps(self.skills), "stderr": ""}
        if rel in init.VALIDATORS.values():
            n = self.fails.get(Path(args[0]).stem, 0)
            lines = ['{"status":"FAIL","check":"frontmatter","detail":"broken"}'] * n + ['{"status":"PASS","check":"name","detail":"ok"}']
            return {"exit": 0, "stdout": "[\n" + ",\n".join(lines) + "\n]\n", "stderr": ""}
        if rel == init.GRADE:
            fails = Path(args[0]).read_text().count('"FAIL"')
            return {"exit": 0, "stdout": f"grade={'A' if not fails else 'C'}\nfails={fails}\nwarns=0\nskipped=0\n", "stderr": ""}
        if rel == init.RETENTION:
            out = "FAIL: directive lost: Never run find /." if self.retention_exit else "ok"
            return {"exit": self.retention_exit, "stdout": "", "stderr": out}
        raise AssertionError(f"unexpected script {rel}")


@pytest.fixture
def scripts(monkeypatch) -> Scripts:
    fake = Scripts()
    monkeypatch.setattr(p, "script", fake)
    return fake


@pytest.fixture
def config_root(repo: Path) -> Path:
    """A committed .claude/ with one skill and one agent, and a CLAUDE.md at the root."""
    (repo / ".claude/skills/tidy").mkdir(parents=True)
    (repo / ".claude/skills/tidy/SKILL.md").write_text("---\nname: tidy\ndescription: Tidy things.\n---\n# tidy\n")
    (repo / ".claude/agents").mkdir()
    (repo / ".claude/agents/helper.md").write_text("---\nname: helper\ndescription: Helps.\ntools: Read\nmodel: sonnet\n---\nbody\n")
    (repo / ".claude/settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}]}}))
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"docs": {}, "db": {}}}))
    (repo / "CLAUDE.md").write_text("# Rules\n\nNever run find /.\nThe repo is a Python app.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "config")
    return repo / ".claude"


def slug() -> str:
    return f"init-{p.today()}"


def audit(repo: Path) -> Path:
    return repo / "crewforge5" / slug() / "audit.md"


def test_new_measures_and_writes_the_audit(run, repo, scripts, config_root):
    out = run("init", "new")
    assert out["ok"] and out["slug"] == slug() and out["target"] == ".claude"
    assert out["next"].endswith(f"/crewforge5:init check --slug {slug()}") and "crewforge5:config-audit" in out["next"]
    text = audit(repo).read_text()
    assert "Status: draft" in text and "Config root: `.claude`" in text and "hooks: 1; MCP servers: db, docs" in text
    before = json.loads((audit(repo).parent / init.MEASURE).read_text())["before"]
    assert before["skills"] == {"tidy": {"desc_chars": 120, "body_chars": 400}}
    assert before["agents"] == {"helper": {"desc_chars": len("Helps.")}}
    assert [c["grade"] for c in before["components"]] == ["A", "A"]
    assert before["context"]["claude_md"][0]["path"] == "CLAUDE.md"
    assert {init.BASELINE, init.GRADE, *init.VALIDATORS.values()} <= set(scripts.calls)
    assert (repo / ".crewforge5.toml").exists() and out["config_created"] is True


def test_new_is_refused_twice_on_one_slug(run, scripts, config_root):
    run("init", "new")
    out = run("init", "new")
    assert out["ok"] is False and "already exists" in out["reason"] and out["next"] == f"/crewforge5:init check --slug {slug()}"


def test_target_defaults_to_the_project_without_a_claude_dir(run, scripts):
    assert run("init", "new")["target"] == "."


def test_target_from_the_argument_and_from_config(run, repo, scripts, toml_config):
    (repo / "cfg/skills").mkdir(parents=True)
    assert run("init", "new", "cfg", "--slug", "init-a")["target"] == "cfg"
    toml_config(init={"target": "cfg"})
    assert run("init", "new", "--slug", "init-b")["target"] == "cfg"
    out = run("init", "new", "missing", "--slug", "init-c")
    assert out["ok"] is False and "not a directory" in out["reason"]


def test_check_refuses_an_unfilled_audit_then_passes(run, repo, scripts, config_root):
    run("init", "new")
    out = run("init", "check")
    assert out["ok"] is False and "unfilled section: Findings" in out["reason"] and "Baseline" not in out["reason"]
    fill(audit(repo), **{**FILLED, "Findings": "- CLAUDE.md is long"})
    out = run("init", "check")
    assert out["ok"] is False and "must start `Important:` or `Nit:`" in out["reason"]
    fill(audit(repo), **FILLED)
    out = run("init", "check")
    assert out["ok"] and out["next"] == f"/crewforge5:init accept --slug {slug()}"


def test_check_without_an_audit_points_at_new(run, scripts):
    out = run("init", "check")
    assert out["ok"] is False and out["next"] == "/crewforge5:init new"


def test_accept_re_measures_records_the_result_and_is_one_checkpoint(run, repo, checkpoint_on, scripts, config_root):
    (repo / ".crewforge5.toml").write_text(p.DEFAULT_CONFIG)
    git(repo, "add", ".crewforge5.toml")
    git(repo, "commit", "-qm", "config")
    run("init", "new")
    assert git(repo, "log", "--format=%s", "-1") == "config", "new never commits"
    fill(audit(repo), **FILLED)
    (repo / "CLAUDE.md").write_text("# Rules\n\nNever run find /.\n")  # the approved edit
    scripts.skills["tidy"]["desc_chars"] = 80
    before = git(repo, "rev-list", "--count", "HEAD")
    out = run("init", "accept")
    assert out["ok"] and out["status"] == "accepted" and out["desc_chars_delta"] == 40
    assert out["changed"] == ["CLAUDE.md"] and "git commit" in out["next"] and "CLAUDE.md" in out["next"]
    assert int(git(repo, "rev-list", "--count", "HEAD")) == int(before) + 1
    assert git(repo, "log", "--format=%s", "-1") == f"init({slug()}): accept — audit.md"
    assert git(repo, "show", "--name-only", "--format=", "HEAD").splitlines() == [f"crewforge5/{slug()}/audit.md", f"crewforge5/{slug()}/measure.json"]
    text = audit(repo).read_text()
    assert "Status: accepted" in text and "DESC_CHARS_BEFORE=126 DESC_CHARS_AFTER=86 DESC_CHARS_DELTA=40" in text
    assert set(json.loads((audit(repo).parent / init.MEASURE).read_text())) == {"before", "after"}
    assert init.RETENTION in scripts.calls
    assert "CLAUDE.md" in git(repo, "status", "--porcelain"), "the config edit is left for the human to commit"


def test_accept_refuses_a_retention_breach(run, repo, checkpoint_on, scripts, config_root):
    run("init", "new")
    fill(audit(repo), **FILLED)
    (repo / "CLAUDE.md").write_text("# Rules\n")
    scripts.retention_exit = 1
    head = git(repo, "rev-parse", "HEAD")
    out = run("init", "accept")
    assert out["ok"] is False and "retention breach" in out["reason"]
    assert out["losses"] == ["CLAUDE.md: FAIL: directive lost: Never run find /."]
    assert "Status: draft" in audit(repo).read_text() and git(repo, "rev-parse", "HEAD") == head


def test_accept_refuses_when_validator_failures_rise(run, repo, scripts, config_root):
    run("init", "new")
    fill(audit(repo), **FILLED)
    scripts.fails["helper"] = 2
    out = run("init", "accept")
    assert out["ok"] is False and "rose from 0 to 2" in out["reason"] and out["below_a"] == ["agent:helper=C"]
    assert "Status: draft" in audit(repo).read_text()


def test_accept_is_refused_before_the_audit_checks(run, repo, scripts, config_root):
    run("init", "new")
    out = run("init", "accept")
    assert out["ok"] is False and "unfilled section" in out["reason"]


def test_status_lists_audits_and_the_next_command(run, repo, scripts, config_root):
    assert run("init", "status") == {"ok": True, "audits": [], "next": "/crewforge5:init new", "stage": "init"}
    run("init", "new")
    out = run("init", "status")
    assert out["audits"] == [{"slug": slug(), "audit": "draft", "next": f"/crewforge5:init check --slug {slug()}"}]
    assert out["next"] == f"/crewforge5:init check --slug {slug()}"
    fill(audit(repo), **FILLED)
    run("init", "accept")
    assert run("init", "status")["audits"][0]["audit"] == "accepted"


def test_init_audits_are_not_features(run, repo, scripts, config_root):
    run("init", "new")
    assert run("status")["features"] == []


def test_init_accept_is_a_checkpoint_boundary():
    assert cli.BOUNDARIES[("init", "accept")] == "accept"


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("jq")), reason="the real gate scripts need bash and jq")
def test_new_measures_through_the_real_scripts(run, repo, config_root):
    out = run("init", "new")
    assert out["ok"], out
    before = json.loads((audit(repo).parent / init.MEASURE).read_text())["before"]
    assert before["skills"]["tidy"]["desc_chars"] == len("Tidy things.")
    assert {c["name"] for c in before["components"]} == {"helper", "tidy"}
    assert all(c["grade"] in "ABCDF" for c in before["components"])
