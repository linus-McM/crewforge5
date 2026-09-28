#!/usr/bin/env bats
# bash_hooks.bats — the bash hooks (bash-guard, learn-capture, learn-nudge)
# follow the one opt-in rule (spec R-G1: on in a project with .crewforge5.toml,
# off via `[hooks] enabled = false` or CREWFORGE5_HOOKS=off, CREWFORGE5_HOOKS=1
# arms nothing), and bash-guard keeps its two rules while heredoc bodies and
# quoted prose never match (R-G4).

source "$(dirname "${BATS_TEST_FILENAME:-${BASH_SOURCE[0]}}")/lib/bats-fallback.sh"

setup() {
  ROOT="$(cd "$BATS_TEST_DIRNAME/../../plugin" && pwd -P)"
  GUARD="$ROOT/hooks/bash-guard.sh"
  TMP="$(cd "$(mktemp -d)" && pwd -P)"
  PROJ="$TMP/proj"
  mkdir -p "$PROJ"
  : > "$PROJ/.crewforge5.toml"
  export CLAUDE_PROJECT_DIR="$PROJ"
  unset CREWFORGE5_HOOKS
}

teardown() {
  cd / || return 0
  rm -rf "$TMP"
}

# Run bash-guard on a command; `output` is the hook's stdout.
_guard() {
  local payload
  payload="$(python3 -c 'import json,sys; print(json.dumps({"tool_input": {"command": sys.argv[1]}}))' "$1")"
  run bash -c 'cd "$1" && printf "%s" "$2" | bash "$3"' _ "$PROJ" "$payload" "$GUARD"
}

_denied() { [ "$status" -eq 0 ] && [[ "$output" == *'"permissionDecision": "deny"'* ]]; }
_silent() { [ "$status" -eq 0 ] && [ -z "$output" ]; }

# --- R-G4: the rules are unchanged -------------------------------------------

@test "bash-guard denies git add -A, --all and ." {
  _guard 'git add -A'; _denied
  _guard 'git status && git add --all'; _denied
  _guard 'git add .'; _denied
}

@test "bash-guard denies find from / or ~" {
  _guard 'find / -name x'; _denied
  _guard 'echo hi; sudo find ~ -name x'; _denied
}

@test "bash-guard allows explicit paths and scoped finds" {
  _guard 'git add .gitignore src/a.py'; _silent
  _guard 'git add -Ax'; _silent
  _guard 'find . -name "*.sh"'; _silent
}

@test "bash-guard still sees a rule split by a line continuation" {
  _guard $'git add \\\n  -A'; _denied
}

# --- R-G4: heredoc bodies and quoted prose never match -----------------------

@test "a heredoc body that mentions a rule is prose" {
  _guard $'cat > notes.md <<\'EOF\'\ngit add -A\nfind / -name x\nEOF'; _silent
  _guard $'python3 - <<EOF\nprint("git add .")\nEOF'; _silent
  _guard $'cat <<-EOF\n\tgit add -A\n\tEOF'; _silent
}

@test "a command after a heredoc is still checked" {
  _guard $'cat <<EOF > x\nnotes\nEOF\ngit add -A'; _denied
}

@test "quoted prose never matches, even across lines" {
  _guard 'git commit -m "never run git add -A"'; _silent
  _guard $'git commit -m "subject\n\ngit add .\nfind / -x"'; _silent
  _guard "echo 'find / is slow'"; _silent
}

# --- R-G1: the opt-in rule ---------------------------------------------------

@test "bash-guard is inert without .crewforge5.toml" {
  rm "$PROJ/.crewforge5.toml"
  _guard 'git add -A'; _silent
}

@test "[hooks] enabled = false turns bash-guard off" {
  printf '[project]\nhome = "crewforge5"\n\n[hooks]\nenabled = false   # off here\n' > "$PROJ/.crewforge5.toml"
  _guard 'git add -A'; _silent
}

@test "enabled = false in another table leaves the hooks on" {
  printf '[workflows]\nenabled = false\n\n[hooks]\nenabled = true\n' > "$PROJ/.crewforge5.toml"
  _guard 'git add -A'; _denied
}

@test "CREWFORGE5_HOOKS=off turns it off; =1 is no longer needed" {
  export CREWFORGE5_HOOKS=off
  _guard 'git add -A'; _silent
  export CREWFORGE5_HOOKS=1
  _guard 'git add -A'; _denied
}

@test "learn-nudge follows the same rule" {
  local ledger="$TMP/state/ledger"
  mkdir -p "$ledger"
  for i in 1 2 3 4 5; do printf '{"n":%s}\n' "$i" >> "$ledger/demo.jsonl"; done
  run env CLAUDE_CONFIG_DIR="$TMP/state" bash -c 'cd "$1" && bash "$2"' _ "$PROJ" "$ROOT/hooks/learn-nudge.sh"
  [[ "$output" == *"Self-improvement ledger"* ]]
  rm "$PROJ/.crewforge5.toml"
  run env CLAUDE_CONFIG_DIR="$TMP/state" bash -c 'cd "$1" && bash "$2"' _ "$PROJ" "$ROOT/hooks/learn-nudge.sh"
  [ -z "$output" ]
}

@test "no shipped hook reads CREWFORGE5_HOOKS=1 any more" {
  run grep -rn 'CREWFORGE5_HOOKS:-0' "$ROOT/hooks" "$ROOT/scripts"
  [ "$status" -eq 1 ]
}
