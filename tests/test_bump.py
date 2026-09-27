"""scripts/bump_version.py — spec R-H6: one bump moves every version-bearing file together."""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import bump_version as bv  # noqa: E402


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / "plugin/.claude-plugin").mkdir(parents=True)
    (tmp_path / "plugin/.claude-plugin/plugin.json").write_text('{\n  "name": "crewforge5",\n  "version": "0.4.4"\n}\n')
    (tmp_path / ".claude-plugin/marketplace.json").write_text('{"plugins": [{"name": "crewforge5", "version": "0.4.4"}]}\n')
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "crewforge5-plugin"\nversion = "0.4.4"\nrequires-python = ">=3.11"\n')
    (tmp_path / "uv.lock").write_text('version = 1\n\n[[package]]\nname = "ruff"\nversion = "0.6.0"\n\n[[package]]\nname = "crewforge5-plugin"\nversion = "0.4.4"\nsource = { virtual = "." }\n')
    return tmp_path


def test_bump_parts():
    assert bv.bump("0.4.4", "patch") == "0.4.5"
    assert bv.bump("0.4.9", "minor") == "0.5.0"
    assert bv.bump("1.4.2", "major") == "2.0.0"
    with pytest.raises(ValueError):
        bv.bump("0.4", "patch")
    with pytest.raises(ValueError):
        bv.bump("0.4.4", "micro")


def test_write_syncs_every_version_file(tree: Path):
    assert bv.current(tree) == "0.4.4"  # plugin.json is the source of truth
    written = bv.write(tree, "0.4.5")
    assert sorted(p.name for p in written) == ["marketplace.json", "plugin.json", "pyproject.toml", "uv.lock"]
    assert json.loads((tree / "plugin/.claude-plugin/plugin.json").read_text())["version"] == "0.4.5"
    assert json.loads((tree / ".claude-plugin/marketplace.json").read_text())["plugins"][0]["version"] == "0.4.5"
    assert 'version = "0.4.5"' in (tree / "pyproject.toml").read_text()
    lock = (tree / "uv.lock").read_text()
    assert 'name = "crewforge5-plugin"\nversion = "0.4.5"' in lock
    assert 'name = "ruff"\nversion = "0.6.0"' in lock  # only our package entry moves
    assert (tree / "plugin/.claude-plugin/plugin.json").read_text().startswith("{\n  ")  # formatting kept


def test_write_skips_optional_files_that_are_absent(tree: Path):
    (tree / "pyproject.toml").unlink()
    (tree / "uv.lock").unlink()
    written = bv.write(tree, "0.5.0")
    assert sorted(p.name for p in written) == ["marketplace.json", "plugin.json"]
    assert bv.current(tree) == "0.5.0"


def test_main_bumps_only_when_head_equals_base(tree: Path, capsys):
    assert bv.main(["--root", str(tree), "--base", "0.4.4", "--part", "patch"]) == 0
    assert "0.4.4 -> 0.4.5" in capsys.readouterr().out
    assert bv.current(tree) == "0.4.5"
    assert bv.main(["--root", str(tree), "--base", "0.4.4", "--part", "patch"]) == 0
    assert "already ahead" in capsys.readouterr().out
    assert bv.current(tree) == "0.4.5"
    assert bv.main(["--root", str(tree), "--base", "0.5.0", "--part", "patch"]) == 1  # head behind base: refuse
    assert "behind" in capsys.readouterr().out
    assert bv.current(tree) == "0.4.5"


def test_main_without_base_always_bumps(tree: Path):
    assert bv.main(["--root", str(tree), "--part", "minor"]) == 0
    assert bv.current(tree) == "0.5.0"


def test_part_from_labels():
    assert bv.part_from_labels(["bug", "minor"]) == "minor"
    assert bv.part_from_labels(["release:minor"]) == "minor"
    assert bv.part_from_labels(["major", "minor"]) == "major"
    assert bv.part_from_labels(["release:major", "patch"]) == "major"
    assert bv.part_from_labels(["Minor "]) == "minor"
    assert bv.part_from_labels([]) == "patch"
    assert bv.part_from_labels([""]) == "patch"


def test_repository_versions_agree():
    """The live tree: every version-bearing file carries plugin.json's version."""
    version = bv.current(REPO)
    market = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
    assert {p["version"] for p in market["plugins"]} == {version}
    assert f'version = "{version}"' in (REPO / "pyproject.toml").read_text()
    lock = REPO / "uv.lock"
    if lock.is_file():  # a bump that skips uv.lock leaves it stale
        assert f'name = "{bv.PACKAGE}"\nversion = "{version}"' in lock.read_text()


def test_changelog_unreleased_heading_becomes_the_release(tree: Path, capsys):
    (tree / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n- a change\n\n## 0.4.4 — 2026-08-26\n\n- older\n")
    assert bv.main(["--root", str(tree), "--part", "patch", "--date", "2026-09-27"]) == 0
    text = (tree / "CHANGELOG.md").read_text()
    assert "## 0.4.5 — 2026-09-27\n\n- a change\n" in text
    assert "## Unreleased" not in text
    assert "## 0.4.4 — 2026-08-26" in text  # past entries are never rewritten
    assert "CHANGELOG.md: 0.4.4 -> 0.4.5" in capsys.readouterr().out


def test_changelog_without_unreleased_still_gets_a_heading(tree: Path):
    (tree / "CHANGELOG.md").write_text("# Changelog\n\n## 0.4.4 — 2026-08-26\n\n- older\n")
    assert bv.main(["--root", str(tree), "--part", "minor", "--date", "2026-09-27"]) == 0
    text = (tree / "CHANGELOG.md").read_text()
    assert text.index("## 0.5.0 — 2026-09-27") < text.index("## 0.4.4 — 2026-08-26")


def test_no_changelog_is_not_an_error(tree: Path):
    assert bv.stamp_changelog(tree, "0.4.5", "2026-09-27") is None


def test_refused_bump_leaves_the_changelog_alone(tree: Path):
    (tree / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n- a change\n")
    assert bv.main(["--root", str(tree), "--base", "0.5.0", "--part", "patch"]) == 1
    assert "## Unreleased" in (tree / "CHANGELOG.md").read_text()
