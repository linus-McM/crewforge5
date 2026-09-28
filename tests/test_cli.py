"""The verdict contract (R-V1, R-V2): one JSON object with ok/reason/next, refusals only through fail()."""

import json
import re
from pathlib import Path

import pytest

from crewforge5 import cli
from crewforge5 import project as p

PACKAGE = Path(cli.__file__).parent

CALLS = [
    ("status",),
    ("status", "--slug", "nope"),
    ("plan", "new", "Feat"),
    ("plan", "new"),
    ("plan", "check"),
    ("plan", "accept"),
    ("design", "new"),
    ("design", "check", "--slug", "feat"),
    ("build", "accept"),
    ("review", "run"),
    ("review", "review"),
    ("review", "evals"),
    ("bogus",),
    ("plan",),
    ("plan", "frobnicate"),
    (),
]


@pytest.mark.parametrize("argv", CALLS, ids=lambda a: " ".join(a) or "<none>")
def test_every_verdict_has_the_schema(run, argv):
    out = run(*argv)
    assert isinstance(out["ok"], bool)
    assert isinstance(out["next"], str) and out["next"]
    if not out["ok"]:
        assert isinstance(out["reason"], str) and out["reason"]
    json.dumps(out)  # serialisable as it stands


def test_entry_prints_exactly_one_json_object(repo, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["crewforge5", "status"])
    assert cli.entry() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is True
    assert captured.err == ""


def test_entry_exits_non_zero_on_a_refusal_and_still_prints_json(repo, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["crewforge5", "design", "new"])
    assert cli.entry() == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and out["stage"] == "design"


def test_usage_errors_are_verdicts_not_stderr(run, capsys):
    out = run("plan", "frobnicate")
    assert out["ok"] is False and out["reason"].startswith("usage:")
    assert capsys.readouterr() == ("", "")


def test_fail_raises_blocked_with_the_verdict():
    with pytest.raises(p.Blocked) as info:
        p.fail("nope", slug="x")
    assert info.value.verdict == {"ok": False, "reason": "nope", "slug": "x"}


def test_no_mechanic_builds_a_refusal_by_hand():
    offenders = [f.name for f in PACKAGE.glob("*.py") if f.name != "project.py" and re.search(r"[\"']ok[\"']\s*:\s*False", f.read_text())]
    assert offenders == []


def test_only_cli_main_catches_blocked():
    catchers = sorted(f.name for f in PACKAGE.glob("*.py") if "except Blocked" in f.read_text() or "except p.Blocked" in f.read_text())
    assert catchers == ["cli.py"]


def test_command_preamble_carries_the_verdict_rules():
    text = (p.TEMPLATES / "command-preamble.md").read_text()
    for clause in ('"${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py"', "uv run --no-project", "act on `ok`", "quote `reason` verbatim", "follow `next`", "Never edit the verdict logic"):
        assert clause in text
