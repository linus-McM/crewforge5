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

# Install the pre-commit hooks (.pre-commit-config.yaml — the same set CI runs)
hooks:
    @uvx pre-commit install

# Run every pre-commit hook over the whole tree, as CI does
precommit:
    @uvx pre-commit run --all-files --show-diff-on-failure

# Release gates: context budget, names, structure, degradation, manifests
gates:
    @bash scripts/budget_check.sh --verbose
    @bash scripts/name_check.sh
    @bash scripts/validate_all.sh
    @bash scripts/verify_degradation.sh
    # Not --strict yet: the plugin root is the repo root until R-H2, so the dev
    # CLAUDE.md there raises one "not loaded as project context" warning. Phase 2
    # (R-H2) moves the package to plugin/ and restores `--strict plugin`.
    @claude plugin validate .claude-plugin/plugin.json
    @claude plugin validate --strict .

# Full gate: tests, lint, pre-commit, release gates
check: test lint precommit gates
