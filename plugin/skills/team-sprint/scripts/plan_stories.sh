#!/usr/bin/env bash
#
# plan_stories.sh — turn an accepted crewforge5 plan.md into the story plan team-sprint runs.
#
#   plan_stories.sh <home>/<slug>/plan.md            # writes <home>/<slug>/sprint-<slug>.md
#   plan_stories.sh --check <sprint-<slug>.md>       # re-verify the provenance line
#
# `/crewforge5:execute --teams` is the only caller. The plan-review stamp that
# team-sprint's Phase 1 used to demand came from the retired planner skills; a
# plan now reaches a sprint only after a human accepted it (`build accept`), so
# that acceptance is the provenance. The story plan carries it as one line under
# the title:
#
#   <!-- crewforge5: source=<plan.md path> status=accepted sha256=<digest of plan.md> -->
#
# and `--check` fails when plan.md is no longer accepted or has changed since.
#
# Each Order-of-work step becomes one story, keyed by its step number:
#   `## Story <n>: <step text>` with the step as its Acceptance Criteria, the
#   red-then-green Definition of Done, `### Touches:` from the backticked paths
#   and the `path::name` test the step names, and `### Depends On:` from an
#   `(after <n>[, <m>])` note in the step (none otherwise; team-sprint's hybrid
#   dependency source still infers edges from overlapping Touches).
#
# stdout: STATUS=OK PLAN=<story plan path> STORIES=<n>, or STATUS=FAIL with the
# reason on stderr. Exit codes: 0 ok | 1 refused | 2 usage | 3 python3 missing.
set -euo pipefail

usage() { echo "usage: plan_stories.sh <plan.md> | --check <sprint-plan.md>" >&2; exit 2; }

MODE=convert
if [ "${1:-}" = "--check" ]; then MODE=check; shift; fi
[ $# -eq 1 ] || usage
command -v python3 >/dev/null 2>&1 || { echo "plan_stories: python3 required" >&2; echo "STATUS=FAIL"; exit 3; }

exec python3 - "$MODE" "$1" <<'PY'
import hashlib, os, re, sys

mode, path = sys.argv[1], sys.argv[2]

def refuse(reason):
    sys.stderr.write(f"plan_stories: {reason}\n")
    print("STATUS=FAIL")
    sys.exit(1)

def accepted(text):
    m = re.search(r"\bStatus:\s*([A-Za-z-]+)", text)
    return bool(m) and m.group(1).lower() == "accepted"

def digest(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

PROV = re.compile(r"^<!-- crewforge5: source=(\S+) status=accepted sha256=([0-9a-f]{64}) -->$", re.M)

if not os.path.isfile(path):
    refuse(f"not found: {path}")

if mode == "check":
    m = PROV.search(open(path, encoding="utf-8").read())
    if not m:
        refuse(f"{path} carries no crewforge5 provenance line; build it with plan_stories.sh <plan.md>")
    source, sha = m.groups()
    if not os.path.isfile(source):
        refuse(f"source plan {source} is gone")
    if not accepted(open(source, encoding="utf-8").read()):
        refuse(f"{source} is no longer accepted; /crewforge5:build accept it again")
    if digest(source) != sha:
        refuse(f"{source} changed since the story plan was built; rebuild it")
    print(f"STATUS=OK PLAN={path}")
    sys.exit(0)

text = open(path, encoding="utf-8").read()
if os.path.basename(path) != "plan.md":
    refuse(f"{path} is not a feature plan.md")
if not accepted(text):
    refuse(f"{path} is not accepted; a human accepts it with /crewforge5:build accept")

def section(name):
    m = re.search(rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return m.group(1) if m else ""

steps = re.findall(r"^\s*(\d+)[.)]\s+(.+)$", section("Order of work"), re.M)
if not steps:
    refuse(f"{path} has no numbered Order-of-work steps")

feature = os.path.dirname(path) or "."
slug = os.path.basename(os.path.abspath(feature))
first = text.splitlines()[0] if text else ""
title = first.lstrip("# ").split(":", 1)[-1].strip() or slug
known = {n for n, _ in steps}

out = [f"# Sprint: {title}", f"<!-- crewforge5: source={path} status=accepted sha256={digest(path)} -->", ""]
for n, body in steps:
    body = body.strip()
    touches = [t.split("::", 1)[0] for t in re.findall(r"`([^`\s]+)`", body) if "/" in t or "." in t]
    test = re.search(r"test:\s*`?([^`\s]+?)(?:::[^\s`]+)?`?(?:\s|$)", body)
    if test and test.group(1) not in touches:
        touches.append(test.group(1))
    after = re.search(r"\(after\s+([\d,\s]+)\)", body)
    deps = [d for d in re.findall(r"\d+", after.group(1)) if d in known and d != n] if after else []
    out += [
        f"## Story {n}: {body}",
        "",
        "### Acceptance Criteria",
        f"- {body}",
        "",
        "### Definition of Done",
        "- The named test was written first and failed for the right reason (RED), then passes (GREEN)",
        "- Story-scoped tests, typecheck and lint pass",
        "",
        f"### Depends On: {', '.join(deps) if deps else 'none'}",
    ]
    if touches:
        out.append(f"### Touches: {', '.join(dict.fromkeys(touches))}")
    out.append("")

target = os.path.join(feature, f"sprint-{slug}.md")
with open(target, "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(f"STATUS=OK PLAN={target} STORIES={len(steps)}")
PY
