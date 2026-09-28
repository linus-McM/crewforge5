#!/usr/bin/env bash
# bash-guard.sh — PreToolUse(Bash) deny guard for the shell rules in rules/git-hygiene.md.
#
# That rule file states two shell rules a model can read and still forget:
# stage explicit paths rather than `git add -A`, and never run `find` from /
# or ~. Prose asks; this enforces. The rules stay documented there for the
# reasoning; the denial happens here so a lapse costs a retry, not a mess.
#
# Contract: reads a PreToolUse payload on stdin, prints a permissionDecision
# of "deny" with a reason when the command matches, and prints nothing at all
# otherwise (silence = defer to normal permission flow).
#
# FAIL OPEN. A guard that cannot parse its input must not block the session:
# every unexpected condition exits 0 silently. A missed denial is recoverable,
# a wedged shell is not.
#
# ON ONLY WHERE ASKED FOR (spec R-G1). Denying `git add -A` on a stranger's
# machine, unannounced, is a bad first impression, so the guard acts only in a
# project with .crewforge5.toml, and `[hooks] enabled = false` turns it off
# there (hooks-on.sh holds the rule every hook shares).
set -u

# shellcheck source=hooks-on.sh
. "$(dirname "${BASH_SOURCE[0]}")/hooks-on.sh" 2>/dev/null || exit 0
crewforge5_hooks_on || exit 0

payload="$(cat 2>/dev/null)" || exit 0
[ -n "$payload" ] || exit 0

# What the rules below match: the command with heredoc bodies dropped, line
# continuations joined, and every quoted span emptied (R-G4). A filename, a
# commit message or a heredoc that merely mentions a pattern is prose, not a
# command, and must never trip the guard. Heredocs are found before quotes are
# emptied, because `<<'EOF'` carries its terminator inside quotes.
bare="$(GUARD_PAYLOAD="$payload" python3 - <<'PY' 2>/dev/null
import json, os, re

try:
    cmd = json.loads(os.environ["GUARD_PAYLOAD"]).get("tool_input", {}).get("command", "") or ""
except Exception:
    raise SystemExit(0)

HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
kept, ends = [], []
for line in cmd.replace("\\\n", " ").splitlines():
    if ends:
        if line.strip() == ends[0]:
            ends.pop(0)
        continue
    kept.append(line)
    ends += [m.group(2) for m in HEREDOC.finditer(line)]
text = "\n".join(kept)
text = re.sub(r"'[^']*'", "''", text, flags=re.S)
text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text, flags=re.S)
print(text)
PY
)" || exit 0
[ -n "$bare" ] || exit 0

deny() {
  python3 -c '
import json,sys
print(json.dumps({"hookSpecificOutput":{
  "hookEventName":"PreToolUse",
  "permissionDecision":"deny",
  "permissionDecisionReason":sys.argv[1]}}))
' "$1" 2>/dev/null
  exit 0
}

# 1. Wholesale staging. `git add .gitignore` and `git add -Ax` must NOT match,
#    so `.` and `-A` are anchored to a word end.
# shellcheck disable=SC2016  # backticks and $HOME below are literal text, not expansions
if printf '%s' "$bare" | grep -qE '(^|[;&|]|&&|\|\|)[[:space:]]*git[[:space:]]+add[[:space:]]+([^;&|]*[[:space:]])?(-A|--all|\.)([[:space:]]|$)'; then
  deny 'CrewForge5 git-hygiene rule: stage explicit paths — `git add <file>`, never `git add -A` / `git add .`. Name the files this change touched. If you genuinely want everything, the user has to ask for it.'
fi

# 2. Unscoped find. Scoped roots (., ./x, "$REPO", relative paths) are fine;
#    only / and the home directory are refused.
# shellcheck disable=SC2016  # literal text, as above
if printf '%s' "$bare" | grep -qE '(^|[;&|]|&&|\|\|)[[:space:]]*(sudo[[:space:]]+)?find[[:space:]]+(/|~|\$HOME)([[:space:]]|$)'; then
  deny 'CrewForge5 git-hygiene rule: never run `find` from / or ~ — scope it to the project tree. Use the repo root, or Glob, which is faster and already scoped.'
fi

exit 0
