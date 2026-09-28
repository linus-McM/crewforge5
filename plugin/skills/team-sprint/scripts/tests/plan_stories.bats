#!/usr/bin/env bats
# plan_stories.bats — the accepted plan.md -> team-sprint story plan converter
# behind `/crewforge5:execute --teams`. Human acceptance replaced the retired
# planner's adversarial-review stamp as team-sprint's provenance.

source "$(dirname "${BATS_TEST_FILENAME:-${BASH_SOURCE[0]}}")/../../../../../scripts/tests/lib/bats-fallback.sh"

setup() {
  SKILL="$(cd "$BATS_TEST_DIRNAME/../.." && pwd -P)"
  CONV="$SKILL/scripts/plan_stories.sh"
  TMP="$(cd "$(mktemp -d)" && pwd -P)"
  cd "$TMP" || return 1
  mkdir -p crewforge5/token-refresh
  PLAN="crewforge5/token-refresh/plan.md"
  printf '%s\n' \
    '# Plan: Token refresh' \
    'From: spec.md (2026-09-28). Status: accepted. Risk: low.' \
    '' \
    '## Files that change' \
    '- src/auth.py' \
    '' \
    '## Order of work' \
    '1. Reject expired tokens in `src/auth.py` — test: tests/test_auth.py::test_expired fails first' \
    '2. Refresh a token near expiry (after 1) — test: tests/test_refresh.py::test_near fails first' \
    '' \
    '## Risks' \
    'none' \
    '' \
    '## Proof' \
    'pytest passes' > "$PLAN"
}

teardown() {
  cd / || return 0
  rm -rf "$TMP"
}

@test "an accepted plan becomes one story per Order-of-work step" {
  run bash "$CONV" "$PLAN"
  [ "$status" -eq 0 ]
  [[ "$output" == *"STATUS=OK PLAN=crewforge5/token-refresh/sprint-token-refresh.md STORIES=2"* ]]
  local out="crewforge5/token-refresh/sprint-token-refresh.md"
  grep -q '^## Story 1: Reject expired tokens' "$out"
  grep -q '^## Story 2: Refresh a token' "$out"
  grep -q '^### Depends On: 1$' "$out"
  grep -q '^### Touches: src/auth.py, tests/test_auth.py$' "$out"
}

@test "the story plan parses into stories.json and passes the plan-path contract" {
  bash "$CONV" "$PLAN" >/dev/null
  local out="crewforge5/token-refresh/sprint-token-refresh.md"
  run bash "$SKILL/scripts/parse_stories.sh" "$out"
  [ "$status" -eq 0 ]
  [ "$(printf '%s' "$output" | jq 'length')" -eq 2 ]
  [ "$(printf '%s' "$output" | jq -c '.[1].depends_on')" = '["1"]' ]
  run bash "$SKILL/scripts/validate_plan_path.sh" "$out"
  [ "$status" -eq 0 ]
}

@test "a draft plan is refused: only a human-accepted plan reaches a sprint" {
  sed -i.bak 's/Status: accepted/Status: draft/' "$PLAN"
  run bash "$CONV" "$PLAN"
  [ "$status" -eq 1 ]
  [[ "$output" == *"STATUS=FAIL"* ]]
  [[ "$output" == *"not accepted"* ]]
}

@test "--check passes a fresh story plan and fails once plan.md changes" {
  bash "$CONV" "$PLAN" >/dev/null
  local out="crewforge5/token-refresh/sprint-token-refresh.md"
  run bash "$CONV" --check "$out"
  [ "$status" -eq 0 ]
  printf '3. Another step — test: tests/t.py::x fails first\n' >> "$PLAN"
  run bash "$CONV" --check "$out"
  [ "$status" -eq 1 ]
  [[ "$output" == *"changed since"* ]]
}

@test "--check fails a plan with no provenance line" {
  printf '# Sprint\n\n## Story 1: x\n' > crewforge5/token-refresh/sprint-x.md
  run bash "$CONV" --check crewforge5/token-refresh/sprint-x.md
  [ "$status" -eq 1 ]
  [[ "$output" == *"no crewforge5 provenance"* ]]
}

@test "no arguments is a usage error" {
  run bash "$CONV"
  [ "$status" -eq 2 ]
}
