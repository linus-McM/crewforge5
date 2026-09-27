# CrewForge5 — dev recipes. Every recipe runs what CI runs (.github/workflows/ci.yml).
# The installable package is plugin/ (spec R-H2); the repo root is dev tooling.

# Start Claude (Opus) in auto permission mode with this plugin loaded
opus:
    @claude --permission-mode auto --model opus --plugin-dir plugin

# Start Claude (Fable) in auto permission mode with this plugin loaded
fable:
    @claude --permission-mode auto --model fable --plugin-dir plugin

# Run every test suite: bats (the team-sprint aggregate also runs its shellcheck + lint_skill) and pytest
test:
    @bash plugin/skills/team-sprint/scripts/tests/run-all.sh
    @bats scripts/tests/
    @bash plugin/skills/team-sprint-planner/scripts/tests/run-all.sh
    @bats plugin/skills/self-improve/scripts/tests/ plugin/skills/sprint-watchdog/tests/ plugin/skills/token-slim/tests/
    @uv run --group dev pytest

# shellcheck the dev and shipped scripts (the pre-commit and CI scope); ruff over the dev Python
lint:
    @find scripts plugin/scripts plugin/skills -name '*.sh' -exec shellcheck {} +
    @uv run --group dev ruff check scripts tests
    @uv run --group dev ruff format --check scripts tests

# Install the pre-commit hooks (.pre-commit-config.yaml — the same set CI runs)
hooks:
    @uvx pre-commit install

# Run every pre-commit hook over the whole tree, as CI does
precommit:
    @uvx pre-commit run --all-files --show-diff-on-failure

# Release gates: context budget, names, structure, degradation, manifests (strict)
gates:
    @bash plugin/scripts/budget_check.sh --verbose
    @bash plugin/scripts/name_check.sh
    @bash plugin/scripts/validate_all.sh
    @bash scripts/verify_degradation.sh
    @claude plugin validate --strict plugin
    @claude plugin validate --strict .

# Full gate: tests, lint, pre-commit, release gates
check: test lint precommit gates
