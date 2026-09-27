"""One entry point: `uv run --no-project scripts/crewforge5.py <stage> <action> [arg] [--slug s]` prints one JSON verdict.

Every verdict carries `ok`, `next`, and `reason` when `ok` is false (spec R-V1). `main` never prints and is the only
place a `Blocked` is caught (R-V2); `entry` prints.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import build, checkpoint, stages, tdd, workflows
from .project import Blocked, fail


def lifecycle(stage: str, action: str):
    """new/check/accept for an artifact stage; only `plan new` takes the positional title."""
    if action == "new":
        return lambda root, arg, ns: stages.new(stage, root, arg if stage == "plan" else None, ns.slug)
    return lambda root, arg, ns: getattr(stages, action)(stage, root, ns.slug)


COMMANDS = {
    **{(s, act): lifecycle(s, act) for s in stages.ORDER for act in ("new", "check", "accept")},
    ("build", "accept"): lambda root, arg, ns: build.accept(root, ns.slug),
    ("build", "red"): lambda root, arg, ns: tdd.cycle(root, ns.slug, "red", arg),
    ("build", "green"): lambda root, arg, ns: tdd.cycle(root, ns.slug, "green", arg),
    ("build", "sync"): lambda root, arg, ns: build.sync(root, ns.slug),
    ("build", "fix"): lambda root, arg, ns: build.fix(root, ns.slug, arg),
    ("workflows", "list"): lambda root, arg, ns: workflows.catalog(root),
    ("workflows", "env"): lambda root, arg, ns: workflows.env(root),
    ("status", None): lambda root, arg, ns: stages.status(root, ns.slug),
}
# Stage boundaries: after a success, checkpoint commits the verdict's `path` with this action label (R-A3).
BOUNDARIES = {(s, "accept"): "accept" for s in stages.ORDER}


class Parser(argparse.ArgumentParser):
    """Usage errors become a verdict instead of a message on stderr and exit 2."""

    def error(self, message: str):
        fail(f"usage: {message}", next=self.format_usage().removeprefix("usage: ").strip())


def parser() -> argparse.ArgumentParser:
    common = Parser(add_help=False)
    common.add_argument("--slug", help="feature slug (default: the most recent feature)")
    ap = Parser(prog="crewforge5")
    sub = ap.add_subparsers(dest="stage", required=True)
    for stage in dict.fromkeys(s for s, _ in COMMANDS):
        actions = [act for s, act in COMMANDS if s == stage and act]
        st = sub.add_parser(stage, parents=[common])
        if actions:
            st.add_argument("action", choices=actions)
            st.add_argument("arg", nargs="?", help="title (plan new), step (build red|green), on|off (build fix)")
    return ap


def main(argv: list[str], root: Path) -> dict:
    stage = argv[0] if argv else None
    try:
        ns = parser().parse_args(argv)
        stage, key = ns.stage, (ns.stage, getattr(ns, "action", None))
        result = COMMANDS[key](root, getattr(ns, "arg", None), ns)
    except Blocked as blocked:
        blocked.verdict.setdefault("next", f"fix the reason, then re-run `crewforge5 {' '.join(argv)}`")
        return {**blocked.verdict, "stage": stage}
    if label := BOUNDARIES.get(key):
        try:
            result["checkpoint"] = checkpoint.commit(root, ns.stage, label, Path(result["path"]))
        except Blocked as blocked:  # a failed checkpoint is reported, never blocks the stage
            result["checkpoint"] = blocked.verdict
    return {**result, "stage": stage}


def entry() -> int:
    result = main(sys.argv[1:], Path.cwd())
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(entry())
