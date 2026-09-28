#!/usr/bin/env bash
# budget_check.sh — the release gate for what this plugin costs before it is used.
#
#   budget_check.sh [--budget N] [--verbose]
#
# Every skill and agent description loads into every session, whether or not the
# skill is ever invoked. That is the plugin's rent. A skill carrying
# `disable-model-invocation: true` is hidden from the always-loaded catalogue and
# pays no rent, which is why hiding one is how a new skill gets paid for.
#
# This is `ceiling.sh`'s measurement applied once to the whole bundle instead of
# per target, with one correction: the catalogue renders `- <name>: <desc>` per
# entry, so the NAME is always-loaded too. Measuring descriptions alone
# understated this bundle by ~116 tokens — enough to hide a breach.
#
# `claude plugin details` reports a larger always-on figure because it charges
# hidden skills as well; verified against a live session, the skills carrying
# `disable-model-invocation: true` do not appear in the skills catalogue at all.
# This gate measures what the session actually carries.
#
# Cost is only half the contract. The bundle is meant to show a fixed public
# surface — the slash commands in commands/ (spec R-S1) and no listed skill — and an extra entry with a short description used to
# pay its tokens and walk through unnoticed. So the listed skills and commands
# are asserted by name as well as charged, independently of the budget.
#
# Exits 0 within budget and correctly shaped, 1 otherwise.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
# The tree measures ~381 tok since spec phase 8 retired the execute skill, the
# sprint-watchdog agent and the hidden flow skills. The budget sits one
# description's worth above that: enough that an honest rewording does not turn
# CI red, too little to absorb a whole new listed surface without somebody
# noticing. Shrinking the tree means lowering this too — slack nobody bounds is
# just a bigger number, and budget_check.bats asserts it from both sides.
#
# It was briefly pinned at the measured total with no slack at all. That reads
# well and behaves badly — every edit to any description became a build break,
# so the pressure was to raise the number rather than think about the cost,
# which is the opposite of what the gate is for.
BUDGET=450
VERBOSE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --budget) BUDGET="${2:?--budget needs a number}"; shift 2 ;;
    --verbose) VERBOSE=1; shift ;;
    *) echo "usage: budget_check.sh [--budget N] [--verbose]" >&2; exit 2 ;;
  esac
done

python3 - "$ROOT" "$BUDGET" "$VERBOSE" <<'PY'
import re, sys
from pathlib import Path

root, budget, verbose = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3] == "1"

# The listed skills: none. Since spec phase 8 every flow is a command and every
# skill is hidden know-how a command names by path (R-P3, R-P4), so any listed
# skill is an entry point nobody chose.
ENTRY_SKILLS = []
# The public slash commands: the stages, the execute shortcut, config hygiene,
# the crew factory and the rules installer.
ENTRY_COMMANDS = ["build", "crew", "design", "execute", "init", "plan", "review", "rules-install"]
# Spec C1: the 0.x skill names survive for one minor release as hidden command
# stubs (`disable-model-invocation: true`) that point at the new command. Hidden,
# they pay no rent; they are allowed only by name, and go in 1.1.0.
RETIRED_STUBS = ["adhd", "adversarial-review", "claude-config", "grill-me", "init-legacy",
                 "master-plan", "plan-legacy", "pre-commit-review-fleet", "sprint-watchdog",
                 "team-feature", "team-sprint-planner", "tech-debt-audit", "use-repo-code"]

def frontmatter(path):
    text = path.read_text(errors="replace")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""

def field(fm, key):
    # Descriptions are single-line in this tree; a folded block would need a
    # YAML parser, and pulling one in for a gate that must run anywhere is a
    # worse trade than failing loudly on a shape we do not use.
    m = re.search(rf"^{key}:\s*(.*)$", fm, re.M)
    return m.group(1).strip() if m else ""

rows, total = [], 0
for skill in sorted((root / "skills").iterdir()):
    f = skill / "SKILL.md"
    if not f.is_file():
        continue
    fm = frontmatter(f)
    if field(fm, "disable-model-invocation").lower() == "true":
        rows.append(("skill", skill.name, 0, "hidden"))
        continue
    n = len(f"- {skill.name}: {field(fm, 'description')}\n")
    total += n
    rows.append(("skill", skill.name, n, ""))

for agent in sorted((root / "agents").glob("*.md")):
    n = len(f"- {agent.stem}: {field(frontmatter(agent), 'description')}\n")
    total += n
    rows.append(("agent", agent.stem, n, ""))

for cmd in sorted((root / "commands").glob("*.md")) if (root / "commands").is_dir() else []:
    fm = frontmatter(cmd)
    if field(fm, "disable-model-invocation").lower() == "true":
        rows.append(("cmd", cmd.stem, 0, "hidden"))
        continue
    n = len(f"- {cmd.stem}: {field(fm, 'description')}\n")
    total += n
    rows.append(("cmd", cmd.stem, n, ""))

# The SessionStart root hook prints one line into every session. It is rent like
# any other always-loaded string, so it is counted here rather than quietly
# excluded because it is not a description.
# A representative install path of typical length; deliberately not a /Users or
# /home path so the CI path-coupling gate does not read it as one machine's path.
HOOK_LINE = "CREWFORGE5_ROOT=/srv/someone00/.claude/plugins/cache/crewforge5/crewforge5/0.1.0"
total += len(HOOK_LINE)
rows.append(("hook", "crewforge5-root (SessionStart line)", len(HOOK_LINE), ""))

tokens = round(total / 4)
if verbose:
    for kind, name, n, note in sorted(rows, key=lambda r: -r[2]):
        print(f"{n:5d}  {kind:5s}  {name}{'  (' + note + ')' if note else ''}")
    print()

hidden = sum(1 for r in rows if r[0] == "skill" and r[3] == "hidden")
stubs = sum(1 for r in rows if r[0] == "cmd" and r[3] == "hidden")
print(f"always-loaded: {total} chars (~{tokens} tok) across "
      f"{sum(1 for r in rows if r[3] != 'hidden')} descriptions; {hidden} skills hidden; "
      f"{stubs} retired-name stubs hidden")
print(f"budget: {budget} tok")

failed = False

listed = [r[1] for r in rows if r[0] == "skill" and r[3] != "hidden"]
unexpected = [n for n in listed if n not in ENTRY_SKILLS]
missing = [n for n in ENTRY_SKILLS if n not in listed]
if unexpected:
    print(f"FAIL: not an entry point but listed: {', '.join(sorted(unexpected))}. "
          f"Add `disable-model-invocation: true` and have a command name it by path. "
          f"Cheap is not the same as free.")
    failed = True
if missing:
    print(f"FAIL: entry point missing from the catalogue: {', '.join(missing)}.")
    failed = True

commands = [r[1] for r in rows if r[0] == "cmd" and r[3] != "hidden"]
stray = [r[1] for r in rows if r[0] == "cmd" and r[3] == "hidden" and r[1] not in RETIRED_STUBS]
if stray:
    print(f"FAIL: hidden command that is not a retired-name stub: {', '.join(sorted(stray))}. "
          f"Only the C1 stubs in RETIRED_STUBS may hide in commands/.")
    failed = True
extra_cmds = [n for n in commands if n not in ENTRY_COMMANDS]
missing_cmds = [n for n in ENTRY_COMMANDS if n not in commands]
if extra_cmds:
    print(f"FAIL: command not in the public surface: {', '.join(sorted(extra_cmds))}. "
          f"A new command is a new entry point; add it to ENTRY_COMMANDS deliberately.")
    failed = True
if missing_cmds:
    print(f"FAIL: command missing from commands/: {', '.join(missing_cmds)}.")
    failed = True

if tokens > budget:
    print(f"FAIL: over budget by {tokens - budget} tok. Hide a skill behind "
          f"`disable-model-invocation: true`, or trim a description. Do not move the number.")
    failed = True

if failed:
    sys.exit(1)
print(f"PASS: {budget - tokens} tok of headroom")
PY
