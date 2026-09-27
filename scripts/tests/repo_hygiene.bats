#!/usr/bin/env bats
# repo_hygiene.bats — structural rules from the cc_sdlc alignment spec, phase 1
# (docs/specs/cc-sdlc-alignment.md). Each test names the requirement it pins.
# They are greps over the tree on purpose: every one of these rules was broken
# once by an edit that looked harmless in review.

source "$(dirname "${BATS_TEST_FILENAME:-${BASH_SOURCE[0]}}")/lib/bats-fallback.sh"

setup() {
  ROOT="$(cd "$BATS_TEST_DIRNAME/../.." && pwd -P)"
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

# --- R-V4: no call site falls back to `.` for the plugin root ----------------

@test "R-V4: no shipped file falls back to the current directory for CREWFORGE5_ROOT" {
  # The pattern is assembled, not written, so this file does not match itself.
  local pat hits
  pat='${CREWFORGE5_ROOT'':-.}'
  # CHANGELOG.md and docs/specs/ quote the retired pattern as history; they are
  # the only places it may appear.
  hits="$(cd "$ROOT" && grep -rnF --exclude-dir=.git --exclude-dir=specs \
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
  found="$(cd "$ROOT" && find . -name 'bats-fallback.sh' -not -path './.git/*')"
  n="$(printf '%s\n' "$found" | grep -c . || true)"
  if [ "$n" -ne 1 ]; then printf 'copies:\n%s\n' "$found"; false; fi
  [ "$found" = "./scripts/tests/lib/bats-fallback.sh" ]
  [ -f "$ROOT/scripts/tests/lib/bats-fallback.sh" ]
  [ ! -L "$ROOT/scripts/tests/lib/bats-fallback.sh" ]
}

# --- R-H3: historical plans no longer ship ----------------------------------

@test "R-H3: no references/docs tree ships inside a skill, and nothing cites one" {
  local dirs hits pat
  pat='references/''docs/'   # assembled so this file does not match itself
  dirs="$(cd "$ROOT" && find skills -path '*/references/docs' -type d)"
  if [ -n "$dirs" ]; then printf 'still present:\n%s\n' "$dirs"; false; fi
  hits="$(cd "$ROOT" && grep -rnF -e "$pat" skills agents scripts hooks rules commands 2>/dev/null || true)"
  if [ -n "$hits" ]; then printf '%s\n' "$hits"; false; fi
  [ -f "$ROOT/docs/adr/README.md" ]
}

# --- R-H5: CI runs every bats suite -----------------------------------------

@test "R-H5: every directory holding .bats files is run by a CI step" {
  local ci d missing="" n=0
  ci="$ROOT/.github/workflows/ci.yml"
  [ -f "$ci" ]
  for d in $(cd "$ROOT" && find . -name '*.bats' -not -path './.git/*' \
               -exec dirname {} \; | sed 's|^\./||' | sort -u); do
    n=$((n + 1))
    grep -qF "$d" "$ci" || missing="$missing $d"
  done
  if [ -n "$missing" ]; then echo "bats suites no CI step names:$missing"; false; fi
  [ "$n" -ge 5 ]
}
