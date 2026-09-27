# CrewForge5

Claude Code plugin under `plugin/` (the installable package; the marketplace installs it as a `git-subdir`). The repo root holds tests, CI, `docs/` and dev tooling, none of which ships. Dogfood output (runs of this plugin on this repo: `crewforge5/`, `.crewforge5/`, `.team-sprint/`, plans, newly generated crews and agents) is committed only on the `dogfood` branch; `main` stays package-only (spec R-H8). The existing root `.claude/` crew stays on `main` because it configures development of this repo. Three entry skills (`/crewforge5:init`, `/crewforge5:plan`, `/crewforge5:execute`) drive 25 hidden sub-skills through a bash + jq flow driver. The alignment with cc_sdlc (Python verdict CLI, slash commands, human-accepted artifacts) is specified in `docs/specs/cc-sdlc-alignment.md`; its §6 order is the roadmap, and its §7 decisions are final.

## Commands
- Test: `just test` (every bats suite, then `uv run --group dev pytest`; all green, never skip or delete a failing test). While iterating, run `bats <file>` directly: `run-all.sh` re-runs the whole team-sprint suite inside `lint_skill.sh`.
- Lint: `just lint` (`shellcheck` over every `.sh` under `scripts/`, `plugin/scripts/` and `plugin/skills/`, which must be clean under shellcheck 0.9, the version Ubuntu CI installs; `ruff check` and `ruff format --check` over the dev Python in `scripts/` and `tests/`).
- Pre-commit: `just precommit` (the `.pre-commit-config.yaml` hooks CI runs); `just hooks` installs them.
- Release gates: `just gates` (`plugin/scripts/{budget_check,name_check,validate_all}.sh`, `scripts/verify_degradation.sh`, `claude plugin validate --strict plugin` and `--strict .`).
- Everything: `just check`. Run it before reporting a task complete and paste the tail. If a test fails, fix the code, not the test.
- Try locally: `just opus` (or `just fable`) runs `claude --plugin-dir plugin`; then `/crewforge5:plan`. Dogfood on the `dogfood` branch, never on `main`.
- Versions: never bump by hand. The CI `version` job runs `scripts/bump_version.py` on each same-repo PR (label `major|minor|patch`, default patch), bumping `plugin/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `pyproject.toml` and `uv.lock` together and dating `## Unreleased` in the CHANGELOG.
- No `just`? Each recipe is a plain command in `justfile`; CI runs the same ones.

## Architecture
- Paths below are under `plugin/` unless they start with `.github/`, `docs/`, `tests/` or root `scripts/{tests,verify_*,bump_version.py}`.
- `skills/{init,plan,execute}/` are the entry points: `SKILL.md` + `phases.json` (`{id,title,doc,gate,required}`) + `phases/phase-N.md`. The model reads a phase doc, does the work, then runs the gate.
- `scripts/flow/` is the shared driver: `flow_next.sh` (what next), `flow_gate.sh` (run and record a gate), `flow_state.sh` (`.crewforge5/<flow>/<subject>/state.json`), `subskill_resolve.sh` (path of a hidden skill). Gates are `bash -c` strings that print `KEY=VALUE` lines.
- `skills/team-sprint/` is execute's engine (phase docs under `references/phases/`, ~30 scripts under `scripts/`, its own bats suite and `lint_skill.sh`). `skills/team-sprint-planner/` is plan's story contract.
- `agents/` are the plugin agents; `hooks/hooks.json` wires the opt-in hooks (`CREWFORGE5_HOOKS=1`) and the SessionStart root announcement.
- Tests: root `scripts/tests/*.bats` (flows, gates, docs surface, repo hygiene; `ROOT` is `plugin/`, `REPO` the checkout), `plugin/skills/*/scripts/tests/` and `plugin/skills/*/tests/` (per-skill, still inside the package until they are ported), and root `tests/` (pytest for `scripts/bump_version.py`). Every bats suite sources the one root `scripts/tests/lib/bats-fallback.sh`. `docs/adr/` holds ADRs; `docs/specs/` holds specs.

## Conventions
- stdout is a machine contract (`KEY=VALUE`, one `STATUS=` line); human text goes to stderr. Exit codes: 0 ok, 1 error, 2 usage.
- Every new `.bats` file sources the root `scripts/tests/lib/bats-fallback.sh` by a path relative to its own directory (five `../` from `plugin/skills/<s>/scripts/tests/`), and its directory is named in `.github/workflows/ci.yml` (`repo_hygiene.bats` enforces both).
- Every agent in `plugin/agents/` declares `name`, `description`, `tools` and `model` (`repo_hygiene.bats`).
- Locate the plugin from the script's own path (`$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)`), or `${CLAUDE_PLUGIN_ROOT}` in skill text the harness expands. Never fall back to `.`: it is the user's repo, not the plugin (`repo_hygiene.bats` fails on the old fallback).
- Commit messages: Conventional Commits, `<type>(<scope>): ...`.
- CHANGELOG: newest release on top, entries under `## Unreleased` (the CI bump turns it into `## X.Y.Z — date`), about 15 lines per release. Longer rationale goes in the PR or an ADR. Never rewrite past entries; they record what was true then.
- The always-loaded context (skill and agent `description`s) is a release gate with ~55 tok of headroom. Lengthening a description can fail `budget_check.sh`.

## Things Claude gets wrong
- Shell state does not survive a tool call. An `export` dies with its own Bash command, so nothing may rely on a variable a previous call set. Carry values in files or state, not in the shell.
- Hooks do not inherit session exports. They are spawned by the harness; only `settings.json`'s `env` block reaches them.
- `${CLAUDE_PLUGIN_ROOT}` is expanded in hook commands and in skill/command text the harness loads. It is not in the Bash tool's environment, and it is not expanded in files read later with Read (phase docs).
- An unset `${VAR}` in a `phases.json` gate expands to nothing, not an error, so the gate silently runs `/skills/...`. The driver derives `CREWFORGE5_ROOT` itself for exactly this reason.
- CI runs macOS too: bash 3.2 (no `mapfile`, no `declare -A`, no `${x^^}`), BSD `sed -i ''`, and `stat -f` means *filesystem* on GNU. Try `stat -c` first.
- A literal `@test` at column 0 inside a heredoc registers a phantom test under Ubuntu's older bats. Build nested fixtures with `printf`.
- An unquoted YAML `description:` containing `: ` silently drops the whole frontmatter. Quote it.
- Hidden sub-skills (`disable-model-invocation: true`) cannot be reached by the `Skill` tool. Resolve them with `scripts/flow/subskill_resolve.sh`.
- A `while` loop fed by a pipe runs in a subshell, so its failures and counters vanish. Feed it with redirection.
- Nothing the plugin needs at runtime may live outside `plugin/`: users get only that directory. Dev-only files (tests, CI, probes, `bump_version.py`) must not go inside it.
- `${CLAUDE_PLUGIN_ROOT}` is `plugin/`, not the repo root; a script's self-located root (`$HERE/..`) is `plugin/` too. Root-level dev scripts reach the package through `$REPO/plugin`.
- This container runs as root, so bats tests that rely on read-only permissions fail locally (`findings_gate.bats` "unreadable plan", `recon_log.bats` AC11/AC11b). They pass in CI; do not "fix" them.
