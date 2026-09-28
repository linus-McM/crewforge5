"""Stage workflows (R-W1-R-W4): the catalog of plugin Workflow scripts and the env that turns the Workflow tool on.

Init, each planning stage and review ship one read-only `workflows/<name>.js`, run as `crewforge5:<name>`; the build command's
implementation step runs `story-executor`, which writes only inside its git worktrees. Its `export const meta`
is written as JSON so this module can read it. Plugin settings cannot set env, so `env` merges `[workflows.env]` into
the project's `.claude/settings.local.json` (never overwriting a value already there) and appends `export` lines to
`CLAUDE_ENV_FILE` when a SessionStart hook provides one. Only CLAUDE_CODE_WORKFLOW* keys, only in projects with a
`.crewforge5.toml`. Off switches: `[workflows] enabled = false`, `auto_env = false`, CREWFORGE5_WORKFLOWS=off.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

from . import project as p

DIR = p.PLUGIN_ROOT / "workflows"
PREFIX = "crewforge5"
SETTINGS = ".claude/settings.local.json"
KEY = re.compile(r"CLAUDE_CODE_WORKFLOW[A-Z0-9_]*")  # a checked-in config must not reach PATH, NODE_OPTIONS or the shell
# step -> the workflow its command runs; every step that runs one has an inline fallback (R-W3). The planning and review
# workflows are read-only; `implement` (the build command's implementation step) writes only inside its worktrees.
CATALOG = {"init": "config-audit", "plan": "intent-scout", "design": "design-panel", "build": "plan-critic", "implement": "story-executor", "review": "review"}
WRITERS = ("story-executor",)


def enabled(root: Path) -> bool:
    return p.enabled(root, "workflows")


def meta(text: str) -> dict:
    """The script's `export const meta = {...}` literal, parsed as JSON; `phases` flattened to their titles."""
    found = re.search(r"^export const meta = (\{.*?^\})", text, re.MULTILINE | re.DOTALL)
    if not found:
        return p.fail("workflow script has no `export const meta = {...}` block")
    try:
        data = json.loads(found.group(1))
    except json.JSONDecodeError as err:
        return p.fail(f"workflow meta is not JSON ({err.msg} at line {err.lineno})")
    return {**data, "phases": [phase["title"] for phase in data.get("phases", [])]}


def catalog(root: Path) -> dict:
    """Every stage's workflow as the command invokes it, with its meta, and whether the layer is on."""
    listed = {}
    for stage, name in CATALOG.items():
        info = meta((DIR / f"{name}.js").read_text())
        listed[stage] = {"name": f"{PREFIX}:{name}", "description": info["description"], "phases": info["phases"]}
    on = enabled(root)
    fallback = "run each workflow step inline, as the command describes"
    return {"ok": True, "enabled": on, "workflows": listed, "next": "run the stage workflow the command names" if on else fallback}


def env(root: Path) -> dict:
    """Merge `[workflows.env]` into the local settings; report which keys were written and which the user kept."""
    conf = p.config(root)["workflows"]
    if not (enabled(root) and conf["auto_env"] and (root / p.CONFIG_NAME).exists()):
        return {"ok": True, "written": [], "kept": [], "skipped": "workflow env is off, or this is not a crewforge5 project", "next": "nothing to do"}
    wanted = {key: str(value) for key, value in conf["env"].items()}
    if bad := [key for key in wanted if not KEY.fullmatch(key)]:
        return p.fail(f"[workflows.env] may only set CLAUDE_CODE_WORKFLOW* variables; refused: {', '.join(bad)}", next=f"remove them from {p.CONFIG_NAME}")
    path = root / SETTINGS
    data = p.read_json(path, {})
    current = data.get("env", {}) if isinstance(data, dict) else None
    if not isinstance(current, dict):
        return p.fail(f"{SETTINGS} is not a JSON object with an `env` object; fix it or set {', '.join(wanted)} yourself", path=str(path))
    merged = {**wanted, **current}  # a value the user set wins
    written = [key for key in wanted if key not in current]
    kept = [key for key in wanted if key in current and str(current[key]) != wanted[key]]
    if written:
        path.parent.mkdir(parents=True, exist_ok=True)
        p.write_json(path, {**data, "env": merged})
    export({key: str(merged[key]) for key in wanted})
    result = {"ok": True, "settings": SETTINGS, "written": written, "kept": kept}
    return {**result, "next": "restart Claude Code so the new env reaches the Workflow tool" if written else "nothing to do"}


def export(values: dict) -> None:
    """Append `export K=V` lines to the SessionStart env file, once each, so this session's Bash sees them."""
    if not (target := os.environ.get("CLAUDE_ENV_FILE")):
        return
    path = Path(target)
    have = path.read_text().splitlines() if path.exists() else []
    if missing := [line for line in (f"export {k}={shlex.quote(v)}" for k, v in values.items()) if line not in have]:
        with path.open("a") as fh:
            fh.write("".join(line + "\n" for line in missing))
