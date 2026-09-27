#!/usr/bin/env python3
"""Bump the CrewForge5 version in every file that carries it (plugin.json is the source of truth), and date the CHANGELOG.

    uv run --no-project scripts/bump_version.py --part patch|minor|major [--base <version>] [--root <dir>] [--date YYYY-MM-DD]

With --base (the version on the target branch): bump only when head equals base, say so when head is
already ahead, exit 1 when head is behind. Used by .github/workflows/ci.yml on pull requests (spec R-H6).
Ported from cc_sdlc's scripts/bump_version.py; CI only, never shipped in plugin/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

PARTS = ("major", "minor", "patch")
PACKAGE = "crewforge5-plugin"  # the [project] name in pyproject.toml, and its entry in uv.lock
JSON_VERSION = re.compile(r'("version"\s*:\s*")[^"]+(")')
PYPROJECT_VERSION = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
LOCK_VERSION = re.compile(rf'^(name = "{PACKAGE}"\nversion = ")([^"]+)(")', re.MULTILINE)
UNRELEASED = re.compile(r"^## Unreleased[ \t]*$", re.MULTILINE)
FIRST_RELEASE = re.compile(r"^## ", re.MULTILINE)


def parse(version: str) -> tuple[int, int, int]:
    nums = version.split(".")
    if len(nums) != 3 or not all(n.isdigit() for n in nums):
        raise ValueError(f"not a MAJOR.MINOR.PATCH version: {version!r}")
    return tuple(int(n) for n in nums)  # type: ignore[return-value]


def bump(version: str, part: str) -> str:
    major, minor, patch = parse(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"part must be one of {PARTS}: {part!r}")


def plugin_manifest(root: Path) -> Path:
    return root / "plugin" / ".claude-plugin" / "plugin.json"


def current(root: Path) -> str:
    return json.loads(plugin_manifest(root).read_text())["version"]


def write(root: Path, version: str) -> list[Path]:
    """Set `version` in plugin.json and marketplace.json, plus pyproject.toml and uv.lock when present,
    keeping each file's formatting. uv.lock is edited in place (our package entry only), so a bump needs
    no `uv lock` resolve."""
    plugin = plugin_manifest(root)
    plugin.write_text(JSON_VERSION.sub(rf"\g<1>{version}\g<2>", plugin.read_text(), count=1))
    market = root / ".claude-plugin" / "marketplace.json"
    market.write_text(JSON_VERSION.sub(rf"\g<1>{version}\g<2>", market.read_text()))
    written = [plugin, market]
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        pyproject.write_text(PYPROJECT_VERSION.sub(rf"\g<1>{version}\g<3>", pyproject.read_text(), count=1))
        written.append(pyproject)
    lock = root / "uv.lock"
    if lock.is_file():
        lock.write_text(LOCK_VERSION.sub(rf"\g<1>{version}\g<3>", lock.read_text(), count=1))
        written.append(lock)
    return written


def stamp_changelog(root: Path, version: str, date: str) -> Path | None:
    """Turn `## Unreleased` into `## <version> — <date>`, the heading docs_surface.bats requires for the
    manifest version. With no Unreleased section, insert an empty-release heading above the newest one, so
    a bump never leaves the manifests naming a version the CHANGELOG lacks."""
    changelog = root / "CHANGELOG.md"
    if not changelog.is_file():
        return None
    text = changelog.read_text()
    heading = f"## {version} — {date}"
    if UNRELEASED.search(text):
        text = UNRELEASED.sub(heading, text, count=1)
    else:
        entry = f"{heading}\n\nNo changelog entry was written for this release.\n\n"
        first = FIRST_RELEASE.search(text)
        text = text[: first.start()] + entry + text[first.start() :] if first else text.rstrip("\n") + "\n\n" + entry.rstrip("\n") + "\n"
    changelog.write_text(text)
    return changelog


def part_from_labels(labels: list[str]) -> str:
    """The largest part a PR label asks for: `major`/`minor`/`patch`, bare or as `release:<part>`. Default patch."""
    wanted = {label.strip().lower() for label in labels}
    return next((part for part in PARTS if part in wanted or f"release:{part}" in wanted), "patch")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--part", choices=PARTS, default="patch")
    ap.add_argument("--base", help="version on the target branch; bump only when head still equals it")
    ap.add_argument("--root", type=Path, default=Path.cwd())
    ap.add_argument("--date", default=dt.datetime.now(dt.UTC).date().isoformat(), help="release date for the CHANGELOG heading (default: today, UTC)")
    ns = ap.parse_args(argv)
    head = current(ns.root)
    if ns.base:
        if parse(head) > parse(ns.base):
            print(f"version already ahead of base: {head} > {ns.base}; nothing to do")
            return 0
        if parse(head) < parse(ns.base):
            print(f"version behind base: {head} < {ns.base}; rebase or merge the target branch first")
            return 1
    new = bump(head, ns.part)
    written = write(ns.root, new)
    changelog = stamp_changelog(ns.root, new, ns.date)
    if changelog:
        written.append(changelog)
    for path in written:
        print(f"{path.relative_to(ns.root)}: {head} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
