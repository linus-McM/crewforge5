#!/usr/bin/env bash
# hooks-on.sh — the one opt-in rule every CrewForge5 hook follows (spec R-G1).
#
# Sourced, not run. `crewforge5_hooks_on` succeeds only when the project has a
# .crewforge5.toml whose [hooks] table does not say `enabled = false`, and
# CREWFORGE5_HOOKS is not `off`. Hooks are spawned by the harness, so that
# variable reaches them only through settings.json's `env` block.
#
# The project is $CLAUDE_PROJECT_DIR when the harness sets it, else the cwd the
# harness started the hook in. No TOML parser: python3 may predate tomllib, and
# this runs on every Bash call, so the [hooks] table is read with awk. A config
# the awk cannot read keeps the hooks on, which is the default anyway.

crewforge5_hooks_on() {
  local dir="${CLAUDE_PROJECT_DIR:-$PWD}" cfg
  [ "${CREWFORGE5_HOOKS:-}" != "off" ] || return 1
  cfg="$dir/.crewforge5.toml"
  [ -f "$cfg" ] || { cfg="$PWD/.crewforge5.toml"; [ -f "$cfg" ] || return 1; }
  ! awk '
    /^[[:space:]]*\[/ { in_hooks = ($0 ~ /^[[:space:]]*\[hooks\][[:space:]]*(#.*)?$/); next }
    in_hooks && /^[[:space:]]*enabled[[:space:]]*=[[:space:]]*false([[:space:]]|#|$)/ { off = 1 }
    END { exit off ? 0 : 1 }
  ' "$cfg" 2>/dev/null
}
