"""Fixtures that drive the crewforge5 verdict CLI in-process and walk a feature through the stages."""

import json
import subprocess
from pathlib import Path

import pytest

from crewforge5 import artifacts, cli


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    """A fresh git repo with one commit; cwd points at it and checkpoints are off."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("x\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-qm", "init")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CREWFORGE5_CHECKPOINT", "off")  # tests commit nothing unless they take `checkpoint_on`
    monkeypatch.delenv("CREWFORGE5_HOME", raising=False)
    return tmp_path


@pytest.fixture
def checkpoint_on(repo: Path, monkeypatch) -> Path:
    """Checkpoints on; list it before any `accepted_*` fixture so their accepts commit."""
    monkeypatch.delenv("CREWFORGE5_CHECKPOINT")
    return repo


@pytest.fixture
def run(repo: Path):
    """Invoke the CLI in-process (never a subprocess of crewforge5.py); return its verdict dict."""

    def _run(*argv: str) -> dict:
        return cli.main([str(a) for a in argv], root=repo)

    return _run


def fill(path: Path, **sections: str) -> None:
    """Replace placeholder bodies under the named sections with real text."""
    text = path.read_text()
    for heading, body in sections.items():
        text = artifacts.set_section(text, heading, body)
    path.write_text(text)


INTENT_BODY = {"Problem": "p", "Proposed outcome": "o", "Affected users and systems": "u", "Constraints": "c", "Open questions": "none"}
SPEC_BODY = {"Requirements": "r", "Design": "d", "Concerns": "none", "Open questions": "none", "Proof": "tests/test_feat.py"}
PLAN_BODY = {
    "Files that change": "- src/feat.py (new)\n- tests/test_feat.py (new)",
    "Order of work": "1. write test_feat, it fails first\n2. implement feat — test: test_feat passes",
    "Risks": "none",
    "Proof": "tests/test_feat.py passes",
}


@pytest.fixture
def accepted_intent(run, repo: Path) -> str:
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    assert run("plan", "accept")["ok"]
    return "feat"


@pytest.fixture
def accepted_spec(run, repo: Path, accepted_intent) -> str:
    run("design", "new")
    fill(repo / "crewforge5/feat/spec.md", **SPEC_BODY)
    assert run("design", "accept")["ok"]
    return "feat"


@pytest.fixture
def accepted_plan(run, repo: Path, accepted_spec) -> str:
    run("build", "new")
    fill(repo / "crewforge5/feat/plan.md", **PLAN_BODY)
    assert run("build", "accept")["ok"]
    return "feat"


@pytest.fixture
def toml_config(repo: Path):
    """Write .crewforge5.toml from {table: {key: value}}; JSON scalars and lists are valid TOML values."""

    def _write(**tables) -> None:
        lines = []
        for table, values in tables.items():
            lines.append(f"[{table}]")
            lines += [f"{k} = {json.dumps(v)}" for k, v in values.items()]
        (repo / ".crewforge5.toml").write_text("\n".join(lines) + "\n")

    return _write
