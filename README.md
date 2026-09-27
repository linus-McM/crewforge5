# CrewForge5 (development repository)

The plugin itself — what users install — is [`plugin/`](plugin/), and its
user documentation is [`plugin/README.md`](plugin/README.md).

```bash
claude plugin marketplace add linus-McM/crewforge5
claude plugin install crewforge5@crewforge5
```

The marketplace (`.claude-plugin/marketplace.json`) installs `plugin/` through a
`git-subdir` source, so nothing at this level ships: tests, CI, `docs/`
(specs and ADRs), the dev tooling and the history stay here. `CLAUDE.md` is the
guide for working on the repo; `docs/specs/cc-sdlc-alignment.md` is the roadmap.

## Layout

| Path | What it is |
| --- | --- |
| `plugin/` | The installable package: `.claude-plugin/plugin.json`, `agents/`, `commands/`, `hooks/`, `rules/`, `skills/`, and the runtime `scripts/` the skills call |
| `.claude-plugin/marketplace.json` | The marketplace entry (`source: git-subdir`, `path: plugin`) |
| `scripts/tests/` | The repo-level bats suite (flow driver, gates, docs surface, repo hygiene) and the one shared `lib/bats-fallback.sh` |
| `scripts/verify_*.sh` | Dev probes: degradation (CI), rule scoping and GNU portability (by hand) |
| `scripts/bump_version.py`, `tests/` | The CI version bump (spec R-H6) and its pytest suite |
| `docs/` | Specs and ADRs |

Dogfood output (the generated crew in `.claude/crews/` and `.claude/agents/`,
`crewforge5/`, `.crewforge5/`) lives only on the `dogfood` branch (spec R-H8).

## Tests

1,030 cases: 1,019 bats cases cover the shell toolchain and the plugin's own
scripts, and 11 pytest cases cover the version bump. CI runs the bats suites on
Ubuntu and macOS, plus the gates, a degradation job and, on pull requests, the
automatic version bump. `just check` runs the lot (`just test`, `just lint`,
`just precommit`, `just gates`); see `CLAUDE.md`.

**Check the exit code, not the tally.** `run-all.sh` runs shellcheck, then bats,
then `lint_skill.sh` — and only the middle step prints `ok` / `not ok` lines. A
green-looking count with a red suite is exactly how a dangling `$REF` citation
survived a full review here. `echo $?` is the signal.

```bash
bash plugin/skills/team-sprint/scripts/tests/run-all.sh   # 649 — the toolchain
bats scripts/tests/                                       # 334 — flow driver, gates, docs surface, validator grading, repo hygiene
bash plugin/skills/team-sprint-planner/scripts/tests/run-all.sh   # 5 — plan read-back
bats plugin/skills/self-improve/scripts/tests/ plugin/skills/sprint-watchdog/tests/ plugin/skills/token-slim/tests/   # 30
uv run --group dev pytest                                 # 11 — scripts/bump_version.py
bash plugin/scripts/budget_check.sh       # always-loaded context budget
bash plugin/scripts/name_check.sh         # frontmatter name matches path
bash plugin/scripts/validate_all.sh       # every skill and agent passes its own validator
bash scripts/verify_degradation.sh        # every entry point survives the base set alone
claude plugin validate --strict plugin && claude plugin validate --strict .
```

Two claims cannot be tested without a real session, so they ship as probes you
run by hand rather than as sentences you have to take on trust:

```bash
bash scripts/verify_rule_scoping.sh   # a paths:-scoped rule loads ONLY on a matching read
```

That one is the assertion the whole rules design rests on. It runs two headless
sessions against an `InstructionsLoaded` hook and checks both directions — a
rule that loads when it shouldn't costs every unrelated session its whole body,
and one that never loads is a convention the model never sees.

On a Mac, also run this before you trust a green suite:

```bash
bash scripts/verify_gnu_portability.sh   # the suite under GNU-semantics stat
```

`stat` is the richest source of works-on-my-Mac bugs here, and it fails
silently. `stat -f %m "$f" || stat -c %Y "$f"` reads as "BSD, else GNU" and is
neither: GNU takes `-f` as `--file-system` and `%m` as the mount point, exits 0,
and the fallback never runs. That one inversion cost 80 failing tests on
ubuntu-latest and zero on macOS. The shim reproduces it in seconds. It models
`stat` only — merged-usr `/bin`, `sed -i`, and flag ordering still need the
Linux CI job.

## Versions and releases

Versions are not bumped by hand. On a pull request from this repository, once
every check is green, the CI `version` job bumps `plugin/.claude-plugin/plugin.json`,
`.claude-plugin/marketplace.json`, `pyproject.toml` and `uv.lock` by the PR's
`major` / `minor` / `patch` label (patch by default; `release:<part>` also
works), dates the CHANGELOG's `## Unreleased` heading, and pushes that commit to
the PR branch. A PR that already moved the version past its base is left alone.
Write CHANGELOG entries under `## Unreleased`.

## License

MIT. See [LICENSE](LICENSE).
