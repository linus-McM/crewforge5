"""Hook handlers, invoked by hooks/hooks.json as `hook.py <event>` with the hook JSON on stdin.

Every handler is inert outside a project with `.crewforge5.toml` (R-G1). Guardrails (pre-edit, post-edit) also stop
under `[hooks] enabled = false` or CREWFORGE5_HOOKS=off.

- session-start (R-W4): run `workflows env` through `cli.main` (so the CLI stays the only place a refusal is caught)
  and report what it wrote.
- pre-edit (R-G2): deny an Edit/Write/MultiEdit under `[build] protected_paths`, and of a test file (`[build]
  test_globs`) while fix mode is on.
- post-edit (R-G3): say when the edited file is missing from the active plan.md's Files that change.

Handlers are cheap (one config read, no git, no network) because they fire on every edit (R-G7). A hook never blocks
a session by failing: any error is silent on stdout, one line on stderr, exit 0.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import artifacts as a
from . import build, cli, stages
from . import project as p


def context(text: str, event: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason}}


def opted_in(root: Path) -> bool:
    return (root / p.CONFIG_NAME).is_file()


def guarding(root: Path) -> bool:
    return opted_in(root) and p.enabled(root, "hooks")


def rel_path(payload: dict, root: Path) -> str | None:
    """The edited file's path inside the project, or None when it lies outside.

    Judged by its name in the project (`..` collapsed, symlinks kept), so a link to an outside file is still the
    protected in-repo name; then by its resolved path, so a symlinked project root still matches.
    """
    raw = payload.get("tool_input", {}).get("file_path")
    if not raw:
        return None
    raw_path = Path(raw) if Path(raw).is_absolute() else root / raw
    lexical = (Path(os.path.abspath(raw_path)), Path(os.path.abspath(root)))  # noqa: PTH100  resolve() would follow the link
    for path, base in (lexical, (raw_path.resolve(), root.resolve())):
        if path.is_relative_to(base):
            return path.relative_to(base).as_posix()
    return None


def session_start(payload: dict, root: Path) -> dict | None:
    if not opted_in(root):
        return None  # never touch a project that has not opted in
    verdict = cli.main(["workflows", "env"], root)
    if not verdict["ok"]:
        return context(f"crewforge5 workflows: {verdict['reason']}.", "SessionStart")
    if verdict.get("written"):
        return context(f"crewforge5 workflows: set {', '.join(verdict['written'])} in {verdict['settings']}; {verdict['next']}.", "SessionStart")
    return None


def pre_edit(payload: dict, root: Path) -> dict | None:
    if not guarding(root) or (rel := rel_path(payload, root)) is None:
        return None
    cfg = p.config(root)["build"]
    if a.matches(rel, cfg["protected_paths"]):
        return deny(f"{rel} is a protected path ([build] protected_paths in {p.CONFIG_NAME}); a change there needs its owner")
    if a.matches(rel, cfg["test_globs"]) and build.fix_on(root):
        return deny(f"{rel} is a test file and fix mode is on: fix the code, not the test (`crewforge5 build fix off` to release)")
    return None


def active_plan(root: Path) -> Path | None:
    """The most recently modified feature whose plan.md a human has accepted."""
    accepted = [f for f in p.features(root) if stages.accepted(f, "plan.md")]
    return max(accepted, key=lambda f: f.stat().st_mtime) if accepted else None


def post_edit(payload: dict, root: Path) -> dict | None:
    if not guarding(root) or (rel := rel_path(payload, root)) is None or build.owned(root, rel):
        return None
    if (feature := active_plan(root)) is None or rel in (planned := build.planned(feature)) or not planned:
        return None
    return context(f"{rel} is not listed in {feature.name}/plan.md 'Files that change'; add it there in the same commit, or revert it (`crewforge5 build sync` checks).", "PostToolUse")


HANDLERS = {"session-start": session_start, "pre-edit": pre_edit, "post-edit": post_edit}


def project_root(payload: dict) -> Path:
    """CLAUDE_PROJECT_DIR when it has opted in, else the payload's cwd, else the process cwd."""
    for candidate in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd")):
        if candidate and opted_in(Path(candidate)):
            return Path(candidate)
    return Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def main(argv: list[str], root: Path | None = None) -> int:
    event = argv[0] if argv else ""
    if event not in HANDLERS:
        print(f"usage: hook.py <{'|'.join(HANDLERS)}>", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
        out = HANDLERS[event](payload, root or project_root(payload))
    except Exception as err:  # fail open (a bad .crewforge5.toml included): a broken hook must never block the session
        print(f"crewforge5 hook {event}: {err}", file=sys.stderr)
        return 0
    if out:
        print(json.dumps(out))
    return 0
