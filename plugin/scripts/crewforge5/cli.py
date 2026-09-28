"""One entry point: `uv run --no-project scripts/crewforge5.py <stage> <action> [arg] [--slug s]` prints one JSON verdict.

Every verdict carries `ok`, `next`, and `reason` when `ok` is false (spec R-V1). `main` never prints and is the only
place a `Blocked` is caught (R-V2); `entry` prints.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import build, checkpoint, crew, docs, evals, init, knowledge, migrate, packs, review, stages, tdd, workflows
from .project import Blocked, fail


def lifecycle(stage: str, action: str):
    """new/check/accept for an artifact stage; only `plan new` takes the positional title."""
    if action == "new":
        return lambda root, arg, ns: stages.new(stage, root, arg if stage == "plan" else None, ns.slug, ns.from_sdlc)
    return lambda root, arg, ns: getattr(stages, action)(stage, root, ns.slug)


COMMANDS = {
    **{(s, act): lifecycle(s, act) for s in stages.ORDER for act in ("new", "check", "accept")},
    ("build", "accept"): lambda root, arg, ns: build.accept(root, ns.slug),
    ("build", "red"): lambda root, arg, ns: tdd.cycle(root, ns.slug, "red", arg),
    ("build", "green"): lambda root, arg, ns: tdd.cycle(root, ns.slug, "green", arg),
    ("build", "sync"): lambda root, arg, ns: build.sync(root, ns.slug),
    ("build", "fix"): lambda root, arg, ns: build.fix(root, ns.slug, arg),
    ("review", "run"): lambda root, arg, ns: review.run(root, ns.slug),
    ("review", "review"): lambda root, arg, ns: review.review(root, ns.slug),
    ("review", "evals"): lambda root, arg, ns: evals.run(root),
    ("init", "new"): lambda root, arg, ns: init.new(root, arg, ns.slug),
    ("init", "check"): lambda root, arg, ns: init.check(root, ns.slug),
    ("init", "accept"): lambda root, arg, ns: init.accept(root, ns.slug),
    ("init", "status"): lambda root, arg, ns: init.status(root),
    ("crew", "survey"): lambda root, arg, ns: crew.survey(root),
    ("crew", "validate"): lambda root, arg, ns: crew.validate(root, arg),
    ("crew", "status"): lambda root, arg, ns: crew.status(root, arg),
    ("knowledge", "bootstrap"): lambda root, arg, ns: knowledge.bootstrap(root, check=arg == "check"),
    ("knowledge", "status"): lambda root, arg, ns: knowledge.status(root),
    ("knowledge", "refresh"): lambda root, arg, ns: knowledge.refresh(root),
    ("knowledge", "check"): lambda root, arg, ns: knowledge.check(root),
    ("knowledge", "pack"): lambda root, arg, ns: packs.build(root, ns.slug, arg, ns.max_tokens),
    ("docs", "render"): lambda root, arg, ns: docs.mechanic("render")(root, arg, ns.slug),
    ("docs", "check"): lambda root, arg, ns: docs.mechanic("check")(root, arg, ns.slug),
    ("docs", "open"): lambda root, arg, ns: docs.mechanic("open")(root, arg, ns.slug),
    ("workflows", "list"): lambda root, arg, ns: workflows.catalog(root),
    ("workflows", "env"): lambda root, arg, ns: workflows.env(root),
    ("status", None): lambda root, arg, ns: stages.status(root, ns.slug),
    ("migrate", None): lambda root, arg, ns: migrate.run(root, arg, ns.slug),
}
# Stages without actions that still take the positional argument.
ARG_STAGES = {"migrate"}
# Stage boundaries: after a success, checkpoint commits the verdict's `path` with this action label (R-A3).
BOUNDARIES = {**{(s, "accept"): "accept" for s in stages.ORDER}, ("init", "accept"): "accept", ("review", "review"): "review"}


class Parser(argparse.ArgumentParser):
    """Usage errors become a verdict instead of a message on stderr and exit 2."""

    def error(self, message: str):
        fail(f"usage: {message}", next=self.format_usage().removeprefix("usage: ").strip())


def parser() -> argparse.ArgumentParser:
    common = Parser(add_help=False)
    common.add_argument("--slug", help="feature slug (default: the most recent feature)")
    common.add_argument("--from-sdlc", dest="from_sdlc", metavar="SLUG", help="build new: take cc_sdlc's accepted sdlc/<slug>/spec.md as the design input")
    common.add_argument("--max-tokens", type=int, dest="max_tokens", help="context-pack budget (knowledge pack)")
    ap = Parser(prog="crewforge5")
    sub = ap.add_subparsers(dest="stage", required=True)
    for stage in dict.fromkeys(s for s, _ in COMMANDS):
        actions = [act for s, act in COMMANDS if s == stage and act]
        st = sub.add_parser(stage, parents=[common])
        if actions:
            st.add_argument("action", choices=actions)
            st.add_argument("arg", nargs="?", help="title (plan new), step (build red|green), on|off (build fix), config root (init new), language (crew), stage (knowledge pack, docs), check (knowledge bootstrap)")
        elif stage in ARG_STAGES:
            st.add_argument("arg", nargs="?", help="the old run to migrate: .crewforge5/<flow>/<subject>/ or docs/plans/<name>.md")
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
