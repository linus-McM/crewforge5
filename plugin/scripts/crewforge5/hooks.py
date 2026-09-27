"""Hook handlers, invoked by hooks/hooks.json as `hook.py <event>` with the hook JSON on stdin.

session-start (R-W4): in a project with `.crewforge5.toml`, run `workflows env` through `cli.main` (so the CLI stays
the only place a refusal is caught) and report what it wrote. A hook never blocks a session: any error is silent on
stdout, one line on stderr, exit 0.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import cli
from . import project as p


def context(text: str, event: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}


def session_start(payload: dict, root: Path) -> dict | None:
    if not (root / p.CONFIG_NAME).is_file():
        return None  # never touch a project that has not opted in
    verdict = cli.main(["workflows", "env"], root)
    if not verdict["ok"]:
        return context(f"crewforge5 workflows: {verdict['reason']}.", "SessionStart")
    if verdict.get("written"):
        return context(f"crewforge5 workflows: set {', '.join(verdict['written'])} in {verdict['settings']}; {verdict['next']}.", "SessionStart")
    return None


HANDLERS = {"session-start": session_start}


def main(argv: list[str], root: Path | None = None) -> int:
    event = argv[0] if argv else ""
    if event not in HANDLERS:
        print(f"usage: hook.py <{'|'.join(HANDLERS)}>", file=sys.stderr)
        return 2
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        payload = json.loads(raw) if raw.strip() else {}
        root = root or Path(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
        out = HANDLERS[event](payload, root)
    except Exception as err:  # fail open: a broken hook must never block the session
        print(f"crewforge5 hook {event}: {err}", file=sys.stderr)
        return 0
    if out:
        print(json.dumps(out))
    return 0
