"""Project-level state: config, the feature home, git helpers and the Blocked verdict.

`config()` is the only reader of `.crewforge5.toml` (spec R-C1). Expected failures raise
through `fail()` (R-V2); only `cli.main` catches them.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import tomllib
from datetime import UTC, datetime
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = PLUGIN_ROOT / "templates"
CONFIG_NAME = ".crewforge5.toml"
DEFAULT_CONFIG = (TEMPLATES / "crewforge5.toml").read_text()
DEFAULTS = tomllib.loads(DEFAULT_CONFIG)
# Layers with an off switch (R-C2): `[<layer>] enabled = false` or CREWFORGE5_<LAYER>=off.
LAYERS = ("checkpoint", "workflows", "hooks")


class Blocked(Exception):
    """A gate refused; `.verdict` is the JSON dict the CLI prints."""

    def __init__(self, reason: str, **extra):
        super().__init__(reason)
        self.verdict = {"ok": False, "reason": reason, **extra}  # the one place a refusal is built (R-V2)


def fail(reason: str, **extra):
    raise Blocked(reason, **extra)


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def config(root: Path) -> dict:
    """The defaults deep-merged with .crewforge5.toml, so every key is always present."""
    path = root / CONFIG_NAME
    if not path.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        return merge(DEFAULTS, tomllib.loads(path.read_text()))
    except tomllib.TOMLDecodeError as err:
        return fail(f"{CONFIG_NAME} is not valid TOML ({err}); fix or delete it", path=str(path))


def ensure_config(root: Path) -> bool:
    """Write the default config when the project has none; True when it was created."""
    path = root / CONFIG_NAME
    if path.exists():
        return False
    path.write_text(DEFAULT_CONFIG)
    return True


def enabled(root: Path, layer: str) -> bool:
    """A layer is on unless CREWFORGE5_<LAYER>=off or `[<layer>] enabled = false`."""
    if os.environ.get(f"CREWFORGE5_{layer.upper()}", "").lower() == "off":
        return False
    return bool(config(root)[layer]["enabled"])


def home(root: Path) -> Path:
    """The feature home (default `crewforge5/`): CREWFORGE5_HOME, else `[project] home`; always inside the project."""
    name = os.environ.get("CREWFORGE5_HOME") or config(root)["project"]["home"]
    path = (root / name).resolve()
    if not name or Path(name).is_absolute() or not path.is_relative_to(root.resolve()) or path == root.resolve():
        fail(f"home {name!r} must be a directory inside the project", next=f"set [project] home in {CONFIG_NAME}")
    return root / name


def features(root: Path) -> list[Path]:
    """Every feature directory (one holding an intent.md), sorted by name."""
    base = home(root)
    return sorted(d for d in base.iterdir() if (d / "intent.md").exists()) if base.is_dir() else []


def feature(root: Path, slug: str | None) -> Path:
    """The named feature, or the most recently modified one; Blocked when there is none."""
    if slug:
        target = home(root) / slug
        if (target / "intent.md").exists():
            return target
        return fail(f"no feature {slug!r} under {rel(root, home(root))}/", next="/crewforge5:plan status")
    if dirs := features(root):
        return max(dirs, key=lambda d: d.stat().st_mtime)
    return fail("no feature found", next='/crewforge5:plan new "<title>"')


def rel(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def run_git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """git without a shell; never raises on a non-zero exit."""
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return subprocess.CompletedProcess(["git", *args], 127, "", "git not found on PATH")


def git(root: Path, *args: str) -> str:
    return run_git(root, *args).stdout.rstrip("\n")


def author(root: Path) -> str:
    return git(root, "config", "user.name") or os.environ.get("USER", "unknown")


def changed_files(root: Path, *paths: str) -> list[str]:
    """Staged, unstaged and untracked paths in one git call, limited to `paths` when given."""
    lines = git(root, "status", "--porcelain", "--untracked-files=all", *(["--", *paths] if paths else [])).splitlines()
    return sorted(line[3:].split(" -> ")[-1] for line in lines)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as err:
        return fail(f"{path.name} is not valid JSON ({err.msg} at line {err.lineno}); fix or delete it", path=str(path))


def write_json(path: Path, data) -> None:
    """Written to a sibling temp file, then renamed into place: a reader never sees half a file."""
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(path)


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def head(root: Path) -> str:
    """The HEAD commit, or "" outside a repository or before the first commit."""
    result = run_git(root, "rev-parse", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else ""


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except json.JSONDecodeError as err:
        return fail(f"{path.name} is not valid JSON lines ({err.msg}); fix or delete the bad line", path=str(path))


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
