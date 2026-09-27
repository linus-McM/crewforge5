#!/usr/bin/env bats
# env_install.bats — contract for the settings.json `env` installer.
#
# WHY THIS FILE EXISTS. This script writes into a file the user owns and may
# have hand-edited, so the merge must preserve every key it did not put there.
# Hooks are no longer armed here (spec R-G1: they act in any project with
# .crewforge5.toml), so `--hooks` is retired: accepted, ignored, and a
# CREWFORGE5_HOOKS=1 an older version wrote is cleaned up.
#
# The claim underneath all of it — that settings.json `env` reaches both the
# Bash tool and hook subprocesses — is undocumented, so `env_install.sh`'s
# header records how it was verified (Claude Code 2.1.246, with a negative
# control). These tests cover the writer; a docs change cannot silently
# invalidate them, but a harness change could, which is why the header names
# the version it was proven against.

setup() {
  ROOT="$(cd "$BATS_TEST_DIRNAME/../../plugin" && pwd -P)"
  ENVI="$ROOT/scripts/env_install.sh"
  TMP="$(cd "$(mktemp -d)" && pwd -P)"
  PROJ="$TMP/proj"
  mkdir -p "$PROJ"
}

teardown() {
  cd / || return 0
  rm -rf "$TMP"
}

_settings() { echo "$PROJ/.claude/settings.json"; }

_key() { # $1 = key — prints the value or <absent>
  python3 - "$(_settings)" "$1" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("<unparseable>"); raise SystemExit(0)
env = d.get("env") if isinstance(d, dict) else None
print(env.get(sys.argv[2], "<absent>") if isinstance(env, dict) else "<absent>")
PY
}

# --- AC: install writes the root ---------------------------------------------

@test "install writes CREWFORGE5_ROOT into the env block" {
  run bash "$ENVI" install --project "$PROJ"
  [ "$status" -eq 0 ]
  [ "$(_key CREWFORGE5_ROOT)" = "$ROOT" ]
}

@test "the file it writes is valid JSON" {
  bash "$ENVI" install --project "$PROJ"
  run python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$(_settings)"
  [ "$status" -eq 0 ]
}

@test "install is idempotent — a second run changes nothing" {
  bash "$ENVI" install --project "$PROJ"
  local first; first="$(cat "$(_settings)")"
  bash "$ENVI" install --project "$PROJ"
  [ "$(cat "$(_settings)")" = "$first" ]
}

# --- AC: the retired --hooks flag arms nothing (R-G1) --------------------------

@test "install never writes CREWFORGE5_HOOKS" {
  bash "$ENVI" install --project "$PROJ"
  [ "$(_key CREWFORGE5_HOOKS)" = "<absent>" ]
}

@test "install --hooks is accepted, ignored, and says why" {
  run bash "$ENVI" install --project "$PROJ" --hooks
  [ "$status" -eq 0 ]
  [[ "$output" == *"--hooks is retired"* ]]
  [ "$(_key CREWFORGE5_HOOKS)" = "<absent>" ]
}

@test "install removes a CREWFORGE5_HOOKS=1 an older version wrote, keeps =off" {
  mkdir -p "$PROJ/.claude"
  printf '{"env": {"CREWFORGE5_HOOKS": "1"}}' > "$(_settings)"
  bash "$ENVI" install --project "$PROJ"
  [ "$(_key CREWFORGE5_HOOKS)" = "<absent>" ]
  printf '{"env": {"CREWFORGE5_HOOKS": "off"}}' > "$(_settings)"
  bash "$ENVI" install --project "$PROJ"
  [ "$(_key CREWFORGE5_HOOKS)" = "off" ]
}

# --- AC: the merge preserves what it did not write ---------------------------

@test "a foreign env key survives install and uninstall" {
  mkdir -p "$PROJ/.claude"
  cat > "$(_settings)" <<'EOF'
{ "env": { "MY_OWN_VAR": "keep-me" } }
EOF
  bash "$ENVI" install --project "$PROJ" --hooks
  [ "$(_key MY_OWN_VAR)" = "keep-me" ]
  bash "$ENVI" uninstall --project "$PROJ"
  [ "$(_key MY_OWN_VAR)" = "keep-me" ]
}

@test "a non-env top-level key survives the merge" {
  mkdir -p "$PROJ/.claude"
  cat > "$(_settings)" <<'EOF'
{ "permissions": { "allow": ["Bash(ls:*)"] } }
EOF
  bash "$ENVI" install --project "$PROJ"
  run python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print(d['permissions']['allow'][0])" "$(_settings)"
  [ "$status" -eq 0 ]
  [ "$output" = "Bash(ls:*)" ]
}

# --- AC: uninstall removes ours and only ours --------------------------------

@test "uninstall removes our keys" {
  bash "$ENVI" install --project "$PROJ" --hooks
  bash "$ENVI" uninstall --project "$PROJ"
  [ "$(_key CREWFORGE5_ROOT)" = "<absent>" ]
  [ "$(_key CREWFORGE5_HOOKS)" = "<absent>" ]
}

# An `env: {}` left behind is scaffolding that says the plugin is still there.
@test "uninstall leaves no empty env block behind" {
  bash "$ENVI" install --project "$PROJ" --hooks
  bash "$ENVI" uninstall --project "$PROJ"
  run python3 -c "
import json,sys
print('env' in json.load(open(sys.argv[1])))" "$(_settings)"
  [ "$output" = "False" ]
}

@test "uninstall on a settings file that never existed is not an error" {
  run bash "$ENVI" uninstall --project "$PROJ"
  [ "$status" -eq 0 ]
}

# --- AC: it refuses rather than writing something wrong ----------------------

# A confidently wrong root breaks every documented command in a way that reads
# as the commands being wrong rather than the path.
@test "install refuses a root with no plugin.json" {
  mkdir -p "$TMP/notplugin"
  run bash "$ENVI" install --project "$PROJ" --root "$TMP/notplugin"
  [ "$status" -eq 1 ]
  [[ "$output" == *"plugin.json"* ]]
  [ ! -f "$(_settings)" ]
}

@test "an unparseable settings file is refused, not clobbered" {
  mkdir -p "$PROJ/.claude"
  printf '{ not json' > "$(_settings)"
  run bash "$ENVI" install --project "$PROJ"
  [ "$status" -ne 0 ]
  [ "$(cat "$(_settings)")" = "{ not json" ]
}

@test "an env that is not an object is refused, not overwritten" {
  mkdir -p "$PROJ/.claude"
  printf '{"env": "nonsense"}' > "$(_settings)"
  run bash "$ENVI" install --project "$PROJ"
  [ "$status" -ne 0 ]
  [[ "$output" == *"not an object"* ]]
}

@test "an unknown flag is a usage error" {
  run bash "$ENVI" install --project "$PROJ" --nonsense
  [ "$status" -eq 2 ]
  [[ "$output" == *"usage:"* ]]
}

@test "an unknown mode is a usage error, not a silent no-op" {
  run bash "$ENVI" bogus
  [ "$status" -eq 2 ]
}

# --- AC: --root and scope ----------------------------------------------------

@test "--root overrides the inferred root" {
  run bash "$ENVI" install --project "$PROJ" --root "$ROOT"
  [ "$status" -eq 0 ]
  [ "$(_key CREWFORGE5_ROOT)" = "$ROOT" ]
}

@test "--user writes under CLAUDE_CONFIG_DIR" {
  export CLAUDE_CONFIG_DIR="$TMP/cfg"
  run bash "$ENVI" install --user
  [ "$status" -eq 0 ]
  [ -f "$TMP/cfg/settings.json" ]
}

# --- AC: report tells the truth without writing ------------------------------

@test "report never creates the settings file" {
  run bash "$ENVI" report --project "$PROJ"
  [ "$status" -eq 0 ]
  [ ! -f "$(_settings)" ]
}

@test "report names the current root and says hooks need no install" {
  bash "$ENVI" install --project "$PROJ"
  run bash "$ENVI" report --project "$PROJ"
  [[ "$output" == *"CREWFORGE5_ROOT=$ROOT"* ]]
  [[ "$output" == *".crewforge5.toml"* ]]
}
