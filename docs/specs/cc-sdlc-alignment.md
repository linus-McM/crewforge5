# Spec: Align CrewForge5 with the cc_sdlc process model
From: review of `linus-McM/cc_sdlc` @ main (plugin 0.6.0) against CrewForge5 0.4.4 (2026-09-26). Status: draft. Risk: high.

> Risk is high because this changes the plugin's public surface (command names, artifact
> locations, state layout) and proposes moving the gate layer to a new runtime.
> Nothing here is implemented yet. The spec is written to be fed to
> `/crewforge5:plan`, which turns it into story plans. The order is in §6.

---

## 1. Why

cc_sdlc and CrewForge5 come from the same author and tackle the same problem: making
Claude Code follow a disciplined engineering loop. They have drifted into two very
different shapes.

| | cc_sdlc (target pattern) | CrewForge5 today |
|---|---|---|
| Entry points | 6 **slash commands** (`plugin/commands/*.md`, ~30 lines each) with `argument-hint` sub-actions (`new / check / accept / status`) | 3 **skills** (`skills/{init,plan,execute}`) plus 26 hidden sub-skills reached through `subskill_resolve.sh` |
| Where the gates live | One Python CLI (`sdlc.py <stage> <action>`). Every call returns a single JSON verdict `{ok, reason, next}`. "Python does the gating; markdown only tells Claude which mechanic to call." | `flow_gate.sh` runs gate strings from `phases.json` through `bash -c`. The output is `KEY=VALUE` lines. Some gates are empty ("judgment"), so no code enforces them. |
| Artifacts | One feature folder `sdlc/<slug>/` holding `intent.md → spec.md → plan.md → tdd.jsonl → test-report.json → review.md`. Each file is a template with a `Status:` line, and the next stage **refuses to start until a human has accepted** the previous one. | Artifacts are split across three places: `.crewforge5/<flow>/<subject>/state.json`, `docs/plans/*.md` (plus `GOAL_IMPACT.md`) and `.team-sprint/sprints/sprint-<slug>/`. Acceptance is an adversarial-review stamp. No human-accept step. |
| Commits | Each stage boundary commits its own output as `<stage>(<slug>): <action> — <artifact>`. | Only the final sprint commit (`build_commit_msg.sh`). |
| TDD | Enforced mechanically. `build red <step>` must see a failure and `build green <step>` a pass, both logged to `tdd.jsonl`. `test run` refuses if no cycle was recorded. `fix on` locks test files. | Enforced by agent instructions and the watchdog. No machine-checked red→green record. |
| Parallel fan-out | A read-only **Workflow script** per stage in `plugin/workflows/*.js`, run as `sdlc:<name>`. Every finding goes to one or two skeptics. Advisory only: the command writes the artifact and the Python gate still decides. | 2 Workflow scripts buried in `skills/team-sprint/references/workflows/`, plus TeamCreate/SendMessage fleets. |
| Hooks | Guardrails that run by default in any project with `.sdlc.toml`: protected paths, test lock in fix mode, "file not in plan.md", knowledge-staleness notices, a release gate. | Off unless `CREWFORGE5_HOOKS=1` is set in the settings.json `env` block: bash-guard, learn-capture, TaskUpdate watchdog. |
| Config | One project file, `.sdlc.toml`, deep-merged over defaults and read in exactly one place (`project.config()`). | Spread over `team-sprint.config.yaml`, `.claude/crews/<lang>.json`, env vars and the `settings.json` env block. |
| Codebase context | Graphify graph plus an OKF knowledge bundle (`sdlc/knowledge/index.md` is read first), and one Repomix **context pack** per stage chosen from the graph (secrets excluded, pinned to a commit). | `recon.sh` (1.1k lines) with providers, and the `graphify` and `use-repo-code` skills. Nothing is shared between stages. |
| Visual review | An Archify stage document per stage, with a freshness gate before accept. | Optional draw.io integration diagram at execute phase 8. |
| Agents | 2 lean, read-only agents: `reviewer` (opus) and `verifier` (sonnet, fresh context). "Never rewrite a command to get past a hook." | 6 plugin agents (855 lines; `sprint-watchdog` alone is 292) with inconsistent frontmatter. |
| Repo hygiene | `plugin/` is the installable package (marketplace `git-subdir`). Root CLAUDE.md has Commands / Architecture / Conventions / *Things Claude gets wrong*. There is a justfile, pre-commit, `claude plugin validate --strict` in CI, automatic version bumps from PR labels, and a separate `dogfood` branch. | No CLAUDE.md. The package is the repo root, so history ships to users (e.g. 3.5k lines of old plans in `skills/team-sprint/references/docs/plans/`). Versions are bumped by hand and CI checks they match. |
| Runtime | Python 3.11 standard library only, run through `uv run --no-project`. pytest and ruff. About 3.3k lines. | Bash plus jq: 13.1k lines of shell and 18k lines of bats. |

Three things in the cc_sdlc model are what make it suit current Claude models, and CrewForge5 lacks all three:

1. **Deterministic gates, thin prose.** Newer models follow short instructions well and
   spend tokens poorly on long ones. cc_sdlc keeps command files short and puts every
   rule that must hold into code that returns a verdict the model acts on.
2. **Artifacts as the contract, humans at the boundaries.** Each stage leaves one
   reviewable file. A person accepts it, and the acceptance is committed. Autonomy grows
   inside a stage, never across a stage boundary.
3. **Native harness features over home-grown ones.** Workflow scripts handle fan-out,
   hooks handle guardrails, fresh-context subagents handle verification, and the plan
   mode that commands enter handles planning. CrewForge5 rebuilt several of these in bash.

## 2. Goals and non-goals

**Goals**
- G1. CrewForge5's flows use cc_sdlc's contract: slash commands with `new/check/accept/status` sub-actions, one JSON-verdict CLI, human-accepted artifacts in one feature folder, and a checkpoint commit at each boundary.
- G2. Whatever must hold is enforced by code or a hook, not by prose. Every phase gate is executable.
- G3. Parallel review and critique runs as read-only Workflow scripts with skeptic verification. Teams/SendMessage stay only where Workflow cannot express the job.
- G4. The shipped package gets smaller: fewer hidden skills, no historical docs, one copy of each helper.
- G5. Repo hygiene matches cc_sdlc: CLAUDE.md, a `plugin/` subdirectory, strict validation in CI, automatic version bumps, pre-commit.

**Non-goals**
- N1. Adding cc_sdlc's `deploy` and `maintain` stages. CrewForge5 stops at a merged commit, and cc_sdlc covers release and operations. §4.9 defines an artifact handoff so the two plugins work together instead.
- N2. Removing CrewForge5's unique value: the **crew factory** (generated per-language agents), **config hygiene** (`init`), and the **self-improve ledger**. These stay, re-shaped to the new contract.
- N3. Rewriting every bats test on day one. Migration is incremental (§6).

## 3. Target shape

```
crewforge5/                         # repo root = dev tooling only
├── CLAUDE.md                       # R-H1
├── justfile  .pre-commit-config.yaml  pyproject.toml (if D1=Python)
├── .claude-plugin/marketplace.json # source: git-subdir → plugin/
├── tests/                          # pytest (or bats) for the CLI
└── plugin/                         # the installable package
    ├── .claude-plugin/plugin.json
    ├── commands/                   # the public surface
    │   ├── init.md                 # /crewforge5:init   new|check|accept|status
    │   ├── plan.md                 # /crewforge5:plan   new|check|accept|status
    │   ├── design.md               # /crewforge5:design new|check|accept   (split from plan, R-S2)
    │   ├── build.md                # /crewforge5:build  new|check|accept|red|green|sync|fix
    │   ├── review.md               # /crewforge5:review run|review|evals
    │   └── crew.md                 # /crewforge5:crew   survey|forge|validate|status
    ├── agents/                     # reviewer, verifier, crew-factory, stack-surveyor (lean)
    ├── workflows/                  # read-only fan-out scripts, run as crewforge5:<name>
    ├── hooks/hooks.json
    ├── scripts/crewforge5.py       # launcher → scripts/crewforge5/ package (or crewforge5.sh, D1)
    ├── skills/                     # only skills a model must load for know-how
    └── templates/                  # intent.md spec.md plan.md REVIEW.md crewforge5.toml
```

Project-side layout (in the user's repo):

```
.crewforge5.toml                    # the only config file (R-C1)
crewforge5/<slug>/                  # one folder per feature (R-A1)
    intent.md  spec.md  plan.md  tdd.jsonl  test-report.json  review.md  learnings.md  docs/
crewforge5/lessons.md               # distilled learnings, committed
.claude/crews/<lang>.json           # unchanged, crew artifacts
```

## 4. Requirements

Every requirement is written so that a test can check it. The workstream prefixes are
used by the story plans.

### 4.1 Verdict CLI: gates in code (R-V)
- **R-V1** One entry point, `crewforge5 <stage> <action> [arg] [--slug s]`, prints exactly one JSON object with `ok` (bool), `reason` (string when `ok` is false), `next` (the command to run next), and action-specific fields. It never writes anything else to stdout.
- **R-V2** Expected failures go through one helper (`fail(reason, **extra)` or its bash equivalent). No mechanic builds `{"ok": false}` by hand. Only the top-level dispatcher catches failures.
- **R-V3** Every phase gate in today's `phases.json` files maps to a CLI action. The empty "judgment" gates (execute phases 2–7) become either (a) a check on an artifact that the judgment produced, or (b) an explicit `accept` that a human performs. A test asserts that no gate is empty.
- **R-V4** Commands call the CLI through `${CLAUDE_PLUGIN_ROOT}` and never depend on `CREWFORGE5_ROOT` being set. The 32 `${CREWFORGE5_ROOT:-.}` fallbacks are removed, and a test fails if the pattern reappears.
- **R-V5** Each command file opens with the same preamble as cc_sdlc: act on `ok`, quote `reason` word for word, follow `next`, never edit the verdict logic.
- **R-V6** `flow_state.sh`, `flow_next.sh`, `flow_gate.sh` and the `phases.json` manifests are retired once every flow runs on the CLI. Per-feature progress is derived from the artifacts on disk (as `sdlc status` does), not from a separate state file. Execution-time state that is not an artifact (sprint wave, story status) moves into `crewforge5/<slug>/build-state.json`, owned by the CLI.

### 4.2 Commands and stages (R-S)
- **R-S1** The public surface is slash commands in `plugin/commands/`, not flow skills. Each has `description`, `argument-hint` and a least-privilege `allowed-tools` list (e.g. `Bash(uv run *)`, `Bash(git *)`, Read, Edit, Write, AskUserQuestion, Agent, Workflow). Each is at most about 40 lines, and a lint test enforces the budget.
- **R-S2** The planning half maps onto cc_sdlc's stages:
  - `plan new "<goal>"` creates `intent.md`. It replaces plan phases 0–3 (intake, ground, diverge, grill). The adhd and grill-me techniques become the interview step and an `intent-scout` workflow.
  - `design new` creates `spec.md`. It covers plan phases 4–5 (tech-debt audit, triage) as the **Concerns** section, and takes the GOAL_IMPACT disposition table as its **Requirements** trace.
  - `build new` writes `plan.md` in plan mode. It replaces plan phases 6–8 and the team-sprint-planner story contract. Stories become the numbered **Order of work** steps, each naming its failing test.
- **R-S3** Only a human accepts. `accept` asks through AskUserQuestion, then sets `Status: accepted` and commits. Each `new` is refused until the previous artifact is accepted. The adversarial-review stamp is kept, but as a precondition checked by `check`, not a substitute for acceptance.
- **R-S4** `/crewforge5:init` keeps its eight phases of config hygiene. It is re-expressed as `init new` (measure → write `crewforge5/init-<date>/audit.md` with findings), `init check` and `init accept` (apply the approved slimming/rectify edits, re-measure, commit `init(<slug>): accept — audit.md`).
- **R-S5** The crew factory becomes its own command, `/crewforge5:crew` (`survey | forge | validate | status`), instead of an implicit step inside execute preflight. `build accept` refuses when the plan's language has no crew with passing validation grades, and `next` names `/crewforge5:crew forge <lang>`.
- **R-S6** `status` with no slug lists the features, which artifacts are accepted, present or missing, and the single next command. It replaces `flow_state.sh list`.

### 4.3 Build and TDD evidence (R-T)
- **R-T1** `build red <step>` runs the configured test command and succeeds only if the tests fail. `build green <step>` succeeds only if they pass. Both append `{step, phase, sha, ts, exit}` to `tdd.jsonl`.
- **R-T2** `review run` refuses when `tdd.jsonl` has no completed red→green pair for each step in `plan.md`.
- **R-T3** `build sync` lists every file changed since the plan was accepted that is missing from plan.md's **Files that change**. The command must either add those files to the plan in the same commit or revert them.
- **R-T4** `build fix on|off` gives the bug-fix mode. While it is on, the pre-edit hook denies edits to test files.
- **R-T5** The generated per-language developer and tester agents take the red/green mechanics as their only way to claim a step is done. The sprint-watchdog's fake-completion checks become assertions over `tdd.jsonl` rather than a 292-line prompt.
- **R-T6** Once all steps are green, the build command runs `/simplify` and then `build sync`, as cc_sdlc does.

### 4.4 Workflows over teams (R-W)
- **R-W1** Workflow scripts move to `plugin/workflows/*.js` and are run as `crewforge5:<name>`. Each script's `export const meta` is written as JSON so the CLI can read it. Phase titles match the phases the script calls. The scripts do not use `Date.now`/`Math.random`, and their agents are read-only. **The command writes the artifact.**
- **R-W2** The minimum catalogue:
  - `intent-scout` (plan)
  - `design-panel` (design)
  - `plan-critic` (build: blast radius, test-first, ordering, coverage, each finding checked by a skeptic)
  - `story-executor` (build: ported from team-sprint, but writes only inside its worktree)
  - `review` (Bugs / Security / Compliance passes against `REVIEW.md`, two skeptics per finding, at most 5 nits). This replaces `pre-commit-review-fleet` and team-sprint phase-7.
  - `config-audit` (init)
- **R-W3** Every command has an inline fallback when `crewforge5 workflows list` reports `enabled: false` or the Workflow tool is missing. The Python/bash gate gives the same verdict either way.
- **R-W4** The session-start hook merges `[workflows.env]` (only `CLAUDE_CODE_WORKFLOW*` keys; anything else is refused) into `.claude/settings.local.json`, but only in projects that have `.crewforge5.toml`. `env_install.sh` and its `CREWFORGE5_ROOT` export are no longer needed.
- **R-W5** TeamCreate/SendMessage are used only for graph-mode parallel stories that need live peer messages, and only if D3 keeps them. `sendmessage-protocol.md` shrinks to match.

### 4.5 Hooks as guardrails (R-G)
- **R-G1** Hooks are on by default in any project with `.crewforge5.toml` and off elsewhere. `CREWFORGE5_HOOKS` is removed. Off switch: `[hooks] enabled = false`.
- **R-G2** pre-edit denies edits under `[build] protected_paths` and, in fix mode, edits to test files.
- **R-G3** post-edit says when the edited file is missing from the active plan.md.
- **R-G4** pre-bash keeps today's `bash-guard` rules (`git add -A/.`, `find /`). Heredoc bodies and quoted prose never match.
- **R-G5** post-bash keeps `learn-capture` (the self-improve ledger). The TaskUpdate watchdog hook is retired in favour of R-T2/R-T5.
- **R-G6** Every plugin agent's instructions say: "If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook." Plugin agents declare no `hooks` or `permissionMode`.
- **R-G7** Hooks never render documents, run networked installs or take more than 10 s. The only exception is session-start, which gets 180 s and only checks.

### 4.6 Artifacts, config and checkpoints (R-A, R-C)
- **R-A1** All flow output for a feature lives in `crewforge5/<slug>/` (configurable home). `.crewforge5/`, `.team-sprint/` and `docs/plans/` are no longer written. `migrate` moves an existing run across once.
- **R-A2** Templates live in `plugin/templates/` (`intent.md`, `spec.md`, `plan.md`, `REVIEW.md`), with the same required sections as cc_sdlc. `check` validates required sections and the `Status:` / `Risk:` metadata. `Risk: high` (auth, PII, payments, migrations, infra) makes `build accept` require a tech lead.
- **R-A3** Checkpoint commits: every `accept`, plus `review review`, commits only the plugin's own output (`crewforge5/` plus `[checkpoint] paths`). It uses a pathspec so staged user work survives, never stages source or tests, and skips during a merge or rebase. The subject is `<stage>(<slug>): <action> — <artifact>` with `(+N files)`. Off switch: `[checkpoint] enabled = false` or `CREWFORGE5_CHECKPOINT=off`.
- **R-C1** `.crewforge5.toml` is the only project config. It is created by the first `new`. It absorbs `team-sprint.config.yaml` (374-line example) and the command section of `.claude/crews/<lang>.json`, and is read in exactly one function.
- **R-C2** Every layer has one off switch in config and one environment variable, and both are documented in the plugin README.

### 4.7 Shared codebase context (R-K)
- **R-K1** Every command begins with `crewforge5 knowledge bootstrap` (idempotent, check-only by default), then reads a knowledge index before raw files. Call-graph questions go to `graphify query` / `graphify affected` before grep.
- **R-K2** `recon.sh` and its providers are replaced by per-stage context packs, as in cc_sdlc's `packs.py`. The seeds come from the stage artifact, grown one graph hop out. The packs are pinned to HEAD, keep secrets out (frozen exclude list plus a secret scan that fails closed), and are passed to workflow agents as `args.pack`, marked as data, never instructions.
- **R-K3** `build accept` and `review review` require a pack built at HEAD. Other stages' packs are advisory.
- **R-K4** If D2 chooses to share, CrewForge5 reads and writes cc_sdlc's `sdlc/knowledge/` bundle when it is present, rather than creating a second one.

### 4.8 Agents and skills (R-P)
- **R-P1** Plugin agents: `reviewer` (opus, read-only, three passes), `verifier` (sonnet, fresh context, runs the tests and exercises the change against plan.md's Proof), `crew-factory`, `stack-surveyor`. `architect-reviewer` and `boundary-reviewer` become lenses inside the `review` / `plan-critic` workflows. `code-reviewer` (both the agent and the duplicate skill) and `sprint-watchdog` are removed.
- **R-P2** Every agent declares `name`, `description`, `tools` and `model`, and a lint test checks it.
- **R-P3** The skills that remain are ones a model loads for know-how, not flow control: `graphify`, `drawio` (or Archify, D4), `playwright-cli`, `ac-validate`, `token-slim`, `context-hygiene`, `skill-validator`, `agent-validator`, `skill-rectifier`, `agent-rectifier`, `self-improve`, `plugin-forge`. `team-sprint`, `team-sprint-planner`, `team-feature`, `master-plan`, `adhd`, `grill-me`, `adversarial-review`, `tech-debt-audit`, `pre-commit-review-fleet`, `sprint-watchdog`, `use-repo-code`, `claude-config` and `code-reviewer` are folded into commands, workflows or the CLI. The target is at most 14 skills, down from 29.
- **R-P4** `subskill_resolve.sh` is removed. Commands name skills and workflows directly.

### 4.9 Interop with cc_sdlc (R-X)
- **R-X1** If `sdlc/<slug>/spec.md` exists and is accepted, `/crewforge5:build new --from-sdlc <slug>` uses it as its design input. CrewForge5 then acts as a crew-powered **build** stage for cc_sdlc.
- **R-X2** CrewForge5's artifact names and sections match cc_sdlc's templates exactly, so cc_sdlc's `test` and `deploy` stages can consume a CrewForge5 feature folder by setting `[sdlc] home = "crewforge5"`. This is a follow-up in the cc_sdlc repo and is listed only so the formats are not allowed to drift.

### 4.10 Repo hygiene (R-H)
- **R-H1** Add a root `CLAUDE.md` with the cc_sdlc sections: Commands (test, lint, validate, try locally), Architecture, Conventions, *Things Claude gets wrong* (seeded from the CHANGELOG's hard-won lessons, e.g. shell state does not survive a tool call and hooks do not inherit session exports).
- **R-H2** Move the package to `plugin/`. The marketplace uses `source: git-subdir`, `path: plugin`. Tests, CI, `docs/` and history stay at the root and no longer ship to users.
- **R-H3** Delete `skills/team-sprint/references/docs/plans/` (8 files, 3.5k lines). The adr folder moves to root `docs/adr/`. Fix the four live references (`recon.sh:35`, `recon.bats:29`, `recon_guard.bats:33`, `state-schema.md:70`) and the dead path at `parse_stories.bats:469`, which always skips.
- **R-H4** Keep one `bats-fallback.sh` (there are three copies today), or none if D1 = Python.
- **R-H5** CI runs every test suite. Four suites run in no job today: self-improve, sprint-watchdog `repo_preflight`, token-slim `check`, team-sprint-planner `plan_readback`. CI also runs `claude plugin validate --strict plugin` and `--strict .`, and pre-commit (shellcheck/ruff, check-json/toml/yaml, detect-private-key, end-of-file). It keeps the degradation job.
- **R-H6** A version-bump job bumps `plugin.json` and `marketplace.json` from the PR's `major|minor|patch` label, as in cc_sdlc's `bump_version.py`, so versions are not bumped by hand.
- **R-H7** A `justfile` provides `test`, `lint`, `check`, `hooks` and `opus`/`fable` (`claude --plugin-dir plugin`).
- **R-H8** Dogfood output (`crewforge5/`, `.claude/crews`, generated `.claude/agents`) lives on a `dogfood` branch. `main` stays package-only.
- **R-H9** CHANGELOG entries are capped at about 15 lines per release. The longer rationale goes in the PR or an ADR.

## 5. Concerns

| # | Concern | Owner |
|---|---|---|
| C1 | **Breaking change for current users.** The flows move from skills to commands, the artifact paths move and the state format changes. Mitigation: a `migrate` action, a 0.5 → 1.0 major bump, and the old skill names kept for one minor release as stubs that point to the new command. | Maintainer |
| C2 | **Runtime rewrite cost (D1).** 13k lines of bash is a lot to port. A strangler migration (§6) keeps each step shippable. | Maintainer |
| C3 | **Workflow tool availability.** Workflows are behind an environment variable and `disableWorkflows`. Every step needs its inline fallback (R-W3) so that no gate depends on Workflow. | Maintainer |
| C4 | **Loss of graph-mode parallelism** if Teams are dropped (D3). Must be measured on a real sprint before removal. | Maintainer |
| C5 | **Security of context packs.** Anything sent to workflow agents must pass the secret exclusion and scan (R-K2). | Maintainer |

## 6. Migration order

Each phase is one or more PRs and leaves the plugin working.

1. **Hygiene first (low risk).** R-H1, R-H3, R-H4, R-H5, R-H7, R-H9, R-P2, R-V4. No change to behaviour.
2. **Package split.** R-H2, R-H6, and strict validation in CI.
3. **The verdict CLI skeleton**, in the language D1 chooses: `status`, `plan new/check/accept`, templates, checkpoint commits (R-V1–2, R-S3, R-S6, R-A2–3, R-C1). The existing `/crewforge5:plan` flow keeps working alongside it.
4. **Planning stages** on the CLI: `plan`, `design` and `build new/accept` (R-S2), with the `intent-scout`, `design-panel` and `plan-critic` workflows (R-W1–3).
5. **Build and TDD**: red/green/sync/fix, and the story-executor workflow in worktrees (R-T1–6, R-G2–3). Run execute's team-sprint alongside it until parity; then retire team-sprint and its recon (R-K2).
6. **Review stage**: `review run/review/evals` with the `reviewer`/`verifier` agents and the `review` workflow (R-P1, R-W2).
7. **Init and crew** re-expressed as commands (R-S4, R-S5).
8. **Retire the flow driver and hidden skills** (R-V6, R-P3, R-P4, R-G5). Major version bump. Remove the compatibility stubs one minor release later.
9. **Interop** with cc_sdlc (R-X1–2, R-K4).

## 7. Open decisions (for the owner)

- **D1: runtime for the gate layer.**
  - **(a) Recommended: port to Python 3.11 standard library under `uv run --no-project`**, the same as cc_sdlc. JSON is native, the two plugins can share code (artifacts, checkpoint, packs), testing uses pytest in-process, and about 4× less code is expected.
  - (b) Keep bash + jq and adopt only the JSON-verdict contract. Less churn, but the bats burden stays.
- **D2: knowledge bundle.** Share cc_sdlc's `sdlc/knowledge/` OKF bundle when it is present (recommended), or keep a CrewForge5-only index.
- **D3: Teams/SendMessage.** Keep them for graph mode only, or drop them in favour of Workflow fan-out plus worktrees (recommended, once C4 has been measured).
- **D4: stage documents.** Adopt Archify with a freshness gate, as cc_sdlc does, or keep draw.io as an optional output.
- **D5: naming.** Keep `/crewforge5:execute` as an alias for `build` plus `review`, or rename outright.

## 8. Proof

- `just check` (tests, lint, `claude plugin validate --strict plugin` and `.`) passes in CI on every PR.
- New tests, one per requirement family:
  - A CLI verdict schema test (R-V1).
  - A no-empty-gates test and a no `${CREWFORGE5_ROOT:-.}` test (R-V3, R-V4).
  - A command-size and frontmatter lint (R-S1, R-P2).
  - A lifecycle test that walks a fixture feature through `plan → design → build → review`: each `new` is refused before `accept`, and each accept makes exactly one checkpoint commit (R-S3, R-A3).
  - A red/green refusal test (R-T1, R-T2).
  - Hook deny tests for protected paths and fix mode (R-G2, R-G4).
  - A workflow `meta` / phase-title drift test (R-W1).
  - A pack secret-exclusion test (R-K2).
- A dogfood run on the `dogfood` branch takes one real CrewForge5 change end to end on the new commands, and its commit log reads as `plan(…)`, `design(…)`, `build(…)`, `review(…)`.
- Package size: `plugin/` has at most 14 skills, no `docs/plans`, and one `bats-fallback.sh` (or none).
