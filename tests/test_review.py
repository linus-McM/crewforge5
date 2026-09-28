"""R-T2, R-A3: `review run` needs complete TDD evidence and writes test-report.json; `review review` validates
review.md and is a checkpoint boundary; `review evals` gates on [evals] threshold (with `claude` stubbed)."""

import json
import stat
from pathlib import Path

import pytest

from conftest import git
from crewforge5 import review

FEATURE = "crewforge5/feat"
REVIEW = "# Review: Feat\n\n## Bugs\n- none\n\n## Security\n- Important: PII in log (src/feat.py:3)\n\n## Compliance\n- Nit: name the helper (src/feat.py:1)\n"


@pytest.fixture
def green(run, accepted_plan, toml_config):
    """Every Order-of-work step has a red->green pair; `extra` adds [commands] keys for `review run`."""

    def _walk(**extra) -> None:
        toml_config(commands={"test": "exit 1"})
        for step in ("1", "2"):
            assert run("build", "red", step)["ok"]
        toml_config(commands={"test": "exit 0", **extra})
        for step in ("1", "2"):
            assert run("build", "green", step)["ok"]

    return _walk


def report(repo: Path) -> dict:
    return json.loads((repo / FEATURE / review.REPORT).read_text())


def test_run_is_refused_until_every_step_has_a_red_green_pair(run, repo, accepted_plan, toml_config):
    toml_config(commands={"test": "exit 1"})
    run("build", "red", "1")
    toml_config(commands={"test": "exit 0"})
    run("build", "green", "1")
    out = run("review", "run")
    assert out["ok"] is False and "no red->green pair for step 2" in out["reason"]
    assert out["missing"] == ["2"] and out["next"] == "crewforge5 build red 2"
    assert not (repo / FEATURE / review.REPORT).exists()


def test_run_waits_for_an_accepted_plan(run, accepted_spec):
    run("build", "new")
    out = run("review", "run")
    assert out["ok"] is False and "plan.md is not accepted" in out["reason"]


def test_run_writes_the_test_report(run, repo, green):
    green(lint="echo linted", build="")
    out = run("review", "run")
    assert out["ok"] and out["failed"] == [] and [r["name"] for r in out["results"]] == ["test", "lint"]
    data = report(repo)
    assert data["passed"] is True and data["steps"] == ["1", "2"] and data["sha"] == git(repo, "rev-parse", "HEAD")
    assert data["results"][1]["tail"] == "linted"
    assert "crewforge5:verifier" in out["next"] and "review review" in out["next"]


def test_a_failing_check_is_reported_and_recorded(run, repo, green):
    green(lint="echo bad-style; exit 3")
    out = run("review", "run")
    assert out["ok"] is False and "fix the code, not the tests" in out["reason"] and out["failed"] == ["lint"]
    assert report(repo)["passed"] is False


def test_the_last_green_points_at_review_run(run, accepted_plan, toml_config):
    toml_config(commands={"test": "exit 1"})
    run("build", "red", "1")
    run("build", "red", "2")
    toml_config(commands={"test": "exit 0"})
    assert "review run" not in run("build", "green", "1")["next"]
    assert "/crewforge5:review run --slug feat" in run("build", "green", "2")["next"]
    assert "/crewforge5:review run --slug feat" in run("build", "sync")["next"]


def test_review_needs_a_passing_report_at_head(run, repo, green):
    green()
    out = run("review", "review")
    assert out["ok"] is False and "test-report.json" in out["reason"] and out["next"] == "/crewforge5:review run --slug feat"
    assert run("review", "run")["ok"]
    (repo / "later.txt").write_text("x\n")
    git(repo, "add", "later.txt")
    git(repo, "commit", "-qm", "later")
    out = run("review", "review")
    assert out["ok"] is False and "stale" in out["reason"]


def test_review_validates_the_findings_file(run, repo, green):
    green()
    run("review", "run")
    out = run("review", "review")
    assert out["ok"] is False and "review.md missing" in out["reason"]
    (repo / FEATURE / "review.md").write_text(REVIEW)
    out = run("review", "review")
    assert out["ok"] and out["important"] == 1 and out["nits"] == 1
    assert "red|green" in out["next"], "an Important finding is addressed with a red/green cycle"


@pytest.mark.parametrize(
    ("body", "problem"),
    [
        ("## Bugs\n- none\n\n## Security\n- none\n", "missing section: Compliance"),
        ("## Bugs\n\n## Security\n- none\n\n## Compliance\n- none\n", "unfilled section: Bugs"),
        ("## Bugs\n- the loop is off by one (src/a.py:3)\n\n## Security\n- none\n\n## Compliance\n- none\n", "must start `Important:` or `Nit:`"),
        ("## Bugs\n- Important: the loop is off by one\n\n## Security\n- none\n\n## Compliance\n- none\n", "path:line"),
        ("## Bugs\n" + "".join(f"- Nit: n{i} (a.py:{i})\n" for i in range(6)) + "\n## Security\n- none\n\n## Compliance\n- none\n", "6 nits"),
    ],
    ids=["missing-pass", "empty-pass", "untagged", "no-location", "too-many-nits"],
)
def test_review_md_shape(body, problem):
    problems, _ = review.findings(f"# Review: x\n\n{body}")
    assert any(problem in p for p in problems), problems


def test_a_clean_review_with_the_nit_overflow_count_passes():
    body = "## Bugs\n- none\n\n## Security\n- None.\n\n## Compliance\n" + "".join(f"- **Nit**: n{i} (lib/x.py:{i})\n" for i in range(5)) + "\n3 more nit(s) not listed.\n"
    assert review.findings(body) == ([], {"important": 0, "nits": 5})


def test_review_is_a_checkpoint_boundary(run, repo, checkpoint_on, green):
    green()
    run("review", "run")
    (repo / FEATURE / "review.md").write_text(REVIEW.replace("Important", "Nit"))
    before = git(repo, "rev-list", "--count", "HEAD")
    out = run("review", "review")
    assert out["ok"] and out["checkpoint"]["committed"] is True
    subject = git(repo, "log", "-1", "--format=%s")
    assert subject.startswith("review(feat): review — review.md")
    assert int(git(repo, "rev-list", "--count", "HEAD")) == int(before) + 1
    committed = git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert f"{FEATURE}/review.md" in committed and f"{FEATURE}/test-report.json" in committed
    assert run("status", "--slug", "feat")["next"] == review.REVIEWED


def test_run_never_commits(run, repo, checkpoint_on, green):
    green()
    head = git(repo, "rev-parse", "HEAD")
    assert run("review", "run")["ok"] and git(repo, "rev-parse", "HEAD") == head


def test_status_walks_from_execute_to_run_to_review(run, repo, accepted_plan, green):
    assert run("status", "--slug", "feat")["next"] == "/crewforge5:execute"
    green()
    assert run("status", "--slug", "feat")["next"] == "/crewforge5:review run --slug feat"
    run("review", "run")
    assert run("status", "--slug", "feat")["next"] == "/crewforge5:review review --slug feat"


# --- review evals: `claude -p` is a stub script ---------------------------------------------------------------


@pytest.fixture
def fake_claude(repo: Path, monkeypatch, tmp_path_factory) -> Path:
    bin_dir = tmp_path_factory.mktemp("bin")
    script = bin_dir / "claude"
    script.write_text('#!/bin/sh\necho "$@" >> "$CLAUDE_ARGS_LOG"\necho \'{"result": "done"}\'\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("CREWFORGE5_CLAUDE_BIN", str(script))
    monkeypatch.setenv("CLAUDE_ARGS_LOG", str(bin_dir / "args.log"))
    return bin_dir / "args.log"


def write_eval(repo: Path, name: str, check: str) -> None:
    (repo / "evals").mkdir(exist_ok=True)
    (repo / "evals" / f"{name}.json").write_text(json.dumps({"prompt": f"do {name}", "allowed_tools": ["Read"], "checks": [check]}))


def test_evals_run_every_eval_and_gate_on_the_threshold(run, repo, fake_claude):
    write_eval(repo, "a", "true")
    write_eval(repo, "b", "false")
    out = run("review", "evals")
    assert out["ok"] is False and out["pass_rate"] == 0.5 and out["threshold"] == 1.0
    assert [r["name"] for r in out["results"]] == ["a", "b"]
    assert "-p do a --output-format json --allowedTools Read" in fake_claude.read_text()
    assert json.loads((repo / "crewforge5/evals-report.json").read_text())["pass_rate"] == 0.5


def test_evals_pass_at_a_lower_threshold(run, repo, fake_claude, toml_config):
    toml_config(evals={"threshold": 0.5})
    write_eval(repo, "a", "true")
    write_eval(repo, "b", "false")
    assert run("review", "evals")["ok"] is True


def test_a_failing_agent_fails_its_eval(run, repo, fake_claude, monkeypatch):
    monkeypatch.setenv("CREWFORGE5_CLAUDE_BIN", "/nonexistent/claude")
    write_eval(repo, "a", "true")
    out = run("review", "evals")
    assert out["ok"] is False and out["results"][0]["agent_exit"] == 127


def test_evals_without_a_suite_is_a_clear_refusal(run):
    out = run("review", "evals")
    assert out["ok"] is False and "evals/" in out["reason"]


def test_an_eval_without_a_prompt_is_refused(run, repo, fake_claude):
    (repo / "evals").mkdir()
    (repo / "evals/a.json").write_text("{}")
    out = run("review", "evals")
    assert out["ok"] is False and "prompt" in out["reason"]
