# CrewForge5 — dev recipes. Every recipe runs what CI runs (.github/workflows/ci.yml).
# The plugin is the repo root until the plugin/ split (spec R-H2), so --plugin-dir is `.`.

# Start Claude (Opus) in auto permission mode with this plugin loaded
opus:
    @claude --permission-mode auto --model opus --plugin-dir .

# Start Claude (Fable) in auto permission mode with this plugin loaded
fable:
    @claude --permission-mode auto --model fable --plugin-dir .

# Run every bats suite (the team-sprint aggregate also runs its shellcheck + lint_skill)
test:
    @bash skills/team-sprint/scripts/tests/run-all.sh
    @bats scripts/tests/
    @bash skills/team-sprint-planner/scripts/tests/run-all.sh
    @bats skills/self-improve/scripts/tests/ skills/sprint-watchdog/tests/ skills/token-slim/tests/

# shellcheck every shipped script
lint:
    @find scripts skills -name '*.sh' -exec shellcheck {} +

# Install a git pre-commit hook that runs `just lint`
hooks:
    #!/usr/bin/env bash
    set -euo pipefail
    hook="$(git rev-parse --git-path hooks)/pre-commit"
    printf '#!/usr/bin/env bash\nexec just lint\n' > "$hook"
    chmod +x "$hook"
    echo "installed $hook (runs: just lint)"

# Release gates: context budget, names, structure, degradation, manifests
gates:
    @bash scripts/budget_check.sh --verbose
    @bash scripts/name_check.sh
    @bash scripts/validate_all.sh
    @bash scripts/verify_degradation.sh
    @claude plugin validate --strict .claude-plugin/plugin.json
    @claude plugin validate --strict .

# Full gate: tests, lint, release gates
check: test lint gates
