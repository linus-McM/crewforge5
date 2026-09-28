"""Repo hygiene the bats suite does not cover (spec R-H1, R-H5, R-H7, R-H9)."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def sections(path: Path) -> dict[str, str]:
    parts = re.split(r"^## (.+?)\s*$", path.read_text(), flags=re.MULTILINE)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def test_claude_md_has_the_cc_sdlc_sections():
    """R-H1: Commands (test, lint, validate, try locally), Architecture, Conventions, Things Claude gets wrong."""
    found = sections(REPO / "CLAUDE.md")
    assert list(found) == ["Commands", "Architecture", "Conventions", "Things Claude gets wrong"]
    commands = found["Commands"]
    for what in ("Test:", "Lint:", "Try locally:", "claude plugin validate --strict plugin"):
        assert what in commands
    wrong = found["Things Claude gets wrong"]
    assert "Shell state does not survive a tool call" in wrong and "Hooks do not inherit session exports" in wrong


@pytest.mark.parametrize("recipe", ["test", "lint", "check", "hooks", "opus", "fable", "gates", "precommit"])
def test_justfile_has_the_recipes(recipe):
    """R-H7."""
    assert re.search(rf"^{recipe}:", (REPO / "justfile").read_text(), re.MULTILINE)


def test_justfile_opus_and_fable_load_the_plugin_directory():
    text = (REPO / "justfile").read_text()
    assert text.count("--plugin-dir plugin") == 2


@pytest.mark.parametrize("hook", ["check-json", "check-toml", "check-yaml", "detect-private-key", "end-of-file-fixer", "shellcheck", "ruff-check", "ruff-format"])
def test_pre_commit_runs_the_r_h5_hooks(hook):
    assert f"- id: {hook}" in (REPO / ".pre-commit-config.yaml").read_text()


def test_ci_runs_pytest_pre_commit_strict_validation_and_degradation():
    """R-H5 (the bats directories are pinned by repo_hygiene.bats)."""
    ci = (REPO / ".github/workflows/ci.yml").read_text()
    for step in (
        "uv run --group dev pytest",
        "uvx pre-commit run --all-files",
        "claude-code plugin validate --strict plugin",
        "claude-code plugin validate --strict .",
        "bash scripts/verify_degradation.sh",
        "scripts/bump_version.py",
    ):
        assert step in ci, f"ci.yml does not run {step}"


def version(heading: str) -> tuple[int, ...] | None:
    found = re.match(r"(\d+)\.(\d+)\.(\d+)", heading)
    return tuple(map(int, found.groups())) if found else None


def groups(body: str) -> list[list[str]]:
    """An entry group: a lead paragraph and the bullets under it, up to the next lead paragraph."""
    out: list[list[str]] = []
    for line in body.splitlines():
        if not line.strip():
            continue
        if not line.startswith(("- ", "  ")) or not out:
            out.append([])
        out[-1].append(line)
    return out


def test_changelog_entries_stay_short():
    """R-H9: about 15 lines per entry from 0.4.5 on (the release that adopted the cap); older entries stay as written."""
    for heading, body in sections(REPO / "CHANGELOG.md").items():
        v = version(heading)
        if heading != "Unreleased" and (v is None or v <= (0, 4, 5)):
            continue
        for group in groups(body):
            assert len(group) <= 15, f"{heading}: the entry starting {group[0][:60]!r} is {len(group)} lines"
