#!/usr/bin/env bats
# repo_hygiene.bats — structural rules from the cc_sdlc alignment spec, phase 1
# (docs/specs/cc-sdlc-alignment.md). Each test names the requirement it pins.
# They are greps over the tree on purpose: every one of these rules was broken
# once by an edit that looked harmless in review.

source "$(dirname "${BATS_TEST_FILENAME:-${BASH_SOURCE[0]}}")/lib/bats-fallback.sh"

setup() {
  # REPO is the dev checkout; ROOT is the installable package under it (R-H2).
  REPO="$(cd "$BATS_TEST_DIRNAME/../.." && pwd -P)"
  ROOT="$REPO/plugin"
}

# Frontmatter block of a markdown file: the lines between the first two `---`.
_frontmatter() {
  awk 'NR == 1 && /^---[[:space:]]*$/ { f = 1; next }
       f && /^---[[:space:]]*$/ { exit }
       f { print }' "$1"
}

# --- R-P2: every agent declares name, description, tools and model ----------

@test "R-P2: every plugin agent declares name, description, tools and model" {
  local f key bad="" n=0
  for f in "$ROOT"/agents/*.md; do
    n=$((n + 1))
    for key in name description tools model; do
      # A key with an empty value is as missing as an absent one.
      _frontmatter "$f" | grep -qE "^${key}:[[:space:]]*[^[:space:]]" \
        || bad="$bad ${f#"$ROOT"/}:$key"
    done
  done
  if [ -n "$bad" ]; then echo "agents missing frontmatter keys:$bad"; false; fi
  # Guard the guard: an empty agents/ would pass vacuously.
  [ "$n" -ge 1 ]
}

# --- R-G6: agents never work around a hook, and declare none of their own ----

@test "R-G6: every plugin agent says never to work around a hook" {
  local f bad="" n=0
  local line='If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook.'
  for f in "$ROOT"/agents/*.md; do
    n=$((n + 1))
    grep -qF "$line" "$f" || bad="$bad ${f#"$ROOT"/}"
  done
  if [ -n "$bad" ]; then echo "agents without the hook line:$bad"; false; fi
  [ "$n" -ge 1 ]
}

@test "R-G6: no plugin agent declares hooks or permissionMode" {
  local f bad=""
  for f in "$ROOT"/agents/*.md; do
    _frontmatter "$f" | grep -qE '^(hooks|permissionMode):' && bad="$bad ${f#"$ROOT"/}"
  done
  if [ -n "$bad" ]; then echo "agents declaring hooks/permissionMode:$bad"; false; fi
}

# --- R-V4: no call site falls back to `.` for the plugin root ----------------

@test "R-V4: no shipped file falls back to the current directory for CREWFORGE5_ROOT" {
  # The pattern is assembled, not written, so this file does not match itself.
  local pat hits
  pat='${CREWFORGE5_ROOT'':-.}'
  # CHANGELOG.md and docs/specs/ quote the retired pattern as history; they are
  # the only places it may appear.
  hits="$(cd "$REPO" && grep -rnF --exclude-dir=.git --exclude-dir=specs \
            --exclude=CHANGELOG.md -e "$pat" . || true)"
  if [ -n "$hits" ]; then
    printf '%s\n' "$hits"
    echo "self-locate the plugin root or use \${CLAUDE_PLUGIN_ROOT} instead"
    false
  fi
}

# --- R-H4: one bats-fallback.sh for the whole repo --------------------------

@test "R-H4: exactly one bats-fallback.sh exists, and it is a regular file" {
  local found n
  found="$(cd "$REPO" && find . -name 'bats-fallback.sh' -not -path './.git/*')"
  n="$(printf '%s\n' "$found" | grep -c . || true)"
  if [ "$n" -ne 1 ]; then printf 'copies:\n%s\n' "$found"; false; fi
  [ "$found" = "./scripts/tests/lib/bats-fallback.sh" ]
  [ -f "$REPO/scripts/tests/lib/bats-fallback.sh" ]
  [ ! -L "$REPO/scripts/tests/lib/bats-fallback.sh" ]
}

# --- R-H3: historical plans no longer ship ----------------------------------

@test "R-H3: no references/docs tree ships inside a skill, and nothing cites one" {
  local dirs hits pat
  pat='references/''docs/'   # assembled so this file does not match itself
  dirs="$(cd "$ROOT" && find skills -path '*/references/docs' -type d)"
  if [ -n "$dirs" ]; then printf 'still present:\n%s\n' "$dirs"; false; fi
  hits="$(cd "$ROOT" && grep -rnF -e "$pat" skills agents scripts hooks rules commands 2>/dev/null || true)"
  if [ -n "$hits" ]; then printf '%s\n' "$hits"; false; fi
  [ -f "$REPO/docs/adr/README.md" ]
}

# --- R-H5: CI runs every bats suite -----------------------------------------

@test "R-H5: every directory holding .bats files is run by a CI step" {
  local ci d missing="" n=0
  ci="$REPO/.github/workflows/ci.yml"
  [ -f "$ci" ]
  for d in $(cd "$REPO" && find . -name '*.bats' -not -path './.git/*' \
               -exec dirname {} \; | sed 's|^\./||' | sort -u); do
    n=$((n + 1))
    grep -qF "$d" "$ci" || missing="$missing $d"
  done
  if [ -n "$missing" ]; then echo "bats suites no CI step names:$missing"; false; fi
  # Guard the guard: scripts/tests, team-sprint, self-improve and token-slim
  # (the planner and sprint-watchdog suites retired with their skills).
  [ "$n" -ge 4 ]
}

# --- R-H2: plugin/ is the installable package --------------------------------

@test "R-H2: the package lives under plugin/ and nothing of it is left at the root" {
  local d
  [ -f "$ROOT/.claude-plugin/plugin.json" ]
  [ ! -e "$REPO/.claude-plugin/plugin.json" ]
  for d in agents commands hooks rules skills; do
    [ -d "$ROOT/$d" ] || { echo "plugin/$d missing"; false; }
    [ ! -e "$REPO/$d" ] || { echo "$d/ still at the repo root"; false; }
  done
}

@test "R-H2: the marketplace installs plugin/ through git-subdir" {
  local m="$REPO/.claude-plugin/marketplace.json"
  [ "$(jq -r '.plugins[0].source.source' "$m")" = "git-subdir" ]
  [ "$(jq -r '.plugins[0].source.path' "$m")" = "plugin" ]
  [ "$(jq -r '.metadata.pluginRoot' "$m")" = "./plugin" ]
}

@test "R-H2: dev-only trees do not ship inside plugin/" {
  local d
  for d in .github docs .claude scripts/tests; do
    [ ! -e "$ROOT/$d" ] || { echo "plugin/$d ships dev tooling"; false; }
  done
  [ ! -e "$ROOT/CLAUDE.md" ]
}

# --- R-H8: dogfood output lives on the `dogfood` branch, not here -------------

@test "R-H8: no dogfood output is tracked on a package branch" {
  local tracked
  # The dogfood branch itself is the one place this output may be committed.
  if [ "$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)" = "dogfood" ]; then
    skip "on the dogfood branch, where this output belongs"
  fi
  tracked="$(git -C "$REPO" ls-files -- crewforge5 .crewforge5 .crewforge5.toml .team-sprint \
               .claude/crews .claude/agents)"
  if [ -n "$tracked" ]; then
    printf 'dogfood output tracked outside the dogfood branch:\n%s\n' "$tracked"
    false
  fi
}
