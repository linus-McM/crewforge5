# CrewForge5

Agents and skills are a resource with a cost. This plugin generates them where
they belong, executes work with them, and stops them rotting.

```
/crewforge5:init    → measure, slim and validate the config you already have
/crewforge5:plan    → a goal becomes crewforge5/<slug>/intent.md, accepted by a human
/crewforge5:design  → the accepted intent becomes spec.md, accepted by a human
/crewforge5:build   → the accepted spec becomes a test-first plan.md, accepted by a human
/crewforge5:review  → the implemented plan is checked, reviewed against REVIEW.md and checkpointed
/crewforge5:execute → the shortcut: build implement then review; or a stamped plan becomes a merged commit
```

That is the whole surface. Everything underneath — the crew factory, the
review fleet, the recon tooling, the distillation pass — is a sub-skill one of
them loads when its phase needs it.

## Install

```bash
claude plugin marketplace add linus-McM/crewforge5   # or a local checkout's path
claude plugin install crewforge5@crewforge5
```

Restart the session. `claude plugin details crewforge5` shows what you now carry.

## The entry points

Always write the namespaced form. A bare `slash-init` reaches Claude Code's own
CLAUDE.md initializer — a different tool doing a different job — and the bare
forms of the others are ambiguous in the same way.

| Command | What it does | Also triggers on |
| --- | --- | --- |
| `/crewforge5:init` | Gated config hygiene — measure, slim, validate, rectify and report a Claude setup's skills, agents and CLAUDE.md | "clean up my Claude config", "audit context load", "rightsize the environment" |
| `/crewforge5:plan` | Stage 1: interview the originator into `intent.md` (`new "<title>" | check | accept | status`) | "plan this feature" |
| `/crewforge5:design` | Stage 2: the accepted intent becomes `spec.md` with Concerns and a Requirements trace | "design this feature" |
| `/crewforge5:build` | Stage 3: plan mode against the accepted spec writes `plan.md`, every step naming its failing test | "write the build plan" |
| `/crewforge5:review` | Stage 4: `run` (test/lint/build into `test-report.json`, refused without red→green evidence), `review` (`review.md` from the review workflow, committed), `evals` | "review this feature" |
| `/crewforge5:execute` | On an accepted `plan.md`, the shortcut for `build implement` then `review run` and `review review`. On a stamped `docs/plans/` plan, a reviewed plan becomes a merged commit — TDD agent fleet in an isolated worktree, coverage, AC/DoD and review-fleet gates, then an integration diagram and distilled learnings | "run a sprint", "execute this plan" |

`plan`, `design`, `build` and `review` are slash commands over the verdict CLI (below).
`init` and `execute` are still flow skills; each is a state machine over a `phases.json` manifest: a phase is offered,
its gate is run, and the verdict is written to state before the next phase is
offered. A gate announced in prose and never run did not happen.

State lives at `<repo>/.crewforge5/<flow>/<subject>/state.json` — **keyed by the
thing the run is about**, not by the flow alone, so a second plan or a second
sprint in one repo starts at phase 0 instead of resuming into the first one's
verdicts. Each flow claims its own subject in phase 0 —
`flow_state.sh <flow> use --from "<goal | config root | plan path>"` derives a
slug from what the run is about — so this is not something you have to do by
hand. `flow_state.sh <flow> list` names the runs a repo holds, `use <subject>`
switches between them, and `reset` discards one to start it over.

A manifest may also name a `status_source` — a command that answers how far the
run has got — and give a phase a `when` that decides whether it is in this run at
all. `crewforge5:execute` uses both: team-sprint owns phases 0–7 and their
per-story loop, so the driver asks it rather than keeping a second, coarser copy,
and the per-story phases swap for the graph-mode wave loop under
`scheduling: graph`.

### What drives which sub-skill

The sub-skills stay on disk and stay callable by name; they are just no longer
in the catalogue, so a flow reaches one through
`scripts/flow/subskill_resolve.sh` rather than through the `Skill` tool.

| Sub-skill | Driven by | Reached in |
| --- | --- | --- |
| `claude-config` | `/crewforge5:init` | phase 0, resolving the live config |
| `token-slim` | `/crewforge5:init` | phases 1, 3 and 7 — baseline, trim, re-measure |
| `context-hygiene` | `/crewforge5:init` | phase 2, passes 1–4 over CLAUDE.md, rules, hooks, MCP |
| `skill-validator` | `/crewforge5:init` | phase 4 |
| `agent-validator` | `/crewforge5:init` | phase 4 |
| `skill-rectifier` | `/crewforge5:init` | phase 5 |
| `agent-rectifier` | `/crewforge5:init` | phase 5 |
| `plan-legacy` | `/crewforge5:plan-legacy` | the old nine-phase bash planning flow, hidden; `plan`, `design` and `build` replace it |
| `use-repo-code` | `/crewforge5:plan-legacy`, `/crewforge5:execute` | plan-legacy phase 1; execute's preflight and recon |
| `adhd` | `/crewforge5:plan-legacy` | phase 2, parallel divergent frames (the Diverge step of `plan new`) |
| `grill-me` | `/crewforge5:plan-legacy` | phase 3, the questioning loop (the Grill step of `plan new`) |
| `team-feature` | `/crewforge5:plan-legacy` | phases 0–3, the interactive ratification half |
| `tech-debt-audit` | `/crewforge5:plan-legacy` | phase 4 (the Concerns audit of `design new`) |
| `master-plan` | `/crewforge5:plan-legacy` | phases 5 and 8 — impact map, coverage check |
| `team-sprint-planner` | `/crewforge5:plan-legacy` | phase 6, plan contract and story shape (the Order of work of `build new`) |
| `adversarial-review` | `/crewforge5:plan-legacy`, `/crewforge5:execute` | plan-legacy phase 7; execute phase 2 under `scheduling: graph` |
| `team-sprint` | `/crewforge5:execute` | phases 0–7 are its phase docs, wrapped unchanged |
| `sprint-watchdog` | `/crewforge5:execute` | phase 0, the pre-sprint audit |
| `pre-commit-review-fleet` | `/crewforge5:execute` | phase 7, over the sprint diff (a stamped plan; `/crewforge5:review` replaces it in spec phase 8) |
| `drawio` | `/crewforge5:execute` | phase 8, the integration diagram |
| `self-improve` | `/crewforge5:execute` | phase 9, distilling the ledger |
| `ac-validate` | — | assigned to a generated crew member by `crew-factory`; no phase drives it |
| `playwright-cli` | — | same, for frontend AC verification |
| `plugin-forge` | — | nothing drives it; reachable by name only |
| `graphify` | `/crewforge5:plan-legacy`, `/crewforge5:execute` | plan-legacy phase 1 and execute phase 0 — the knowledge-graph half of recon |

## What it costs you

Skill and agent descriptions load into **every** session whether or not you use
them. That is the plugin's rent, and it is measured rather than asserted:

```bash
bash "$CREWFORGE5_ROOT/scripts/budget_check.sh" --verbose
```

The bundle is **~480 tokens** always-loaded across 13 catalogue entries, against
a budget of **550** — one description's worth of headroom, so rewording a
trigger phrase does not turn the build red, while a whole new listed surface
still cannot slip in unpriced. The other **25 skills** carry
`disable-model-invocation: true`, so they cost nothing until a flow resolves one
or you call it by name. That discipline is the only reason a bundle this size is
affordable, and `budget_check.sh` fails the build over the budget rather than
moving it.

Cost is only half of what the gate asserts. It also checks *which* skills are
listed: exactly the `init` and `execute` skills and the `plan`, `design`, `build`,
`review` and `rules-install` commands. An extra entry point with a short description used
to pay its tokens and walk through unnoticed.

`claude plugin details crewforge5` reports a larger always-on number because its
projection charges hidden skills too. Verified against a live session, hidden
skills do not appear in the catalogue at all; `budget_check.sh` measures what
the session actually carries, including the one line the root hook prints.

## `$CREWFORGE5_ROOT`

Plugin skills document commands that live inside the plugin tree, and the
install path is one you would not guess. A `SessionStart` hook prints the path
once per session and writes it to `$XDG_STATE_HOME/crewforge5/root`.

Set it once, per install, and every session afterwards has it:

```bash
bash "$(cat "${XDG_STATE_HOME:-$HOME/.local/state}/crewforge5/root")/scripts/env_install.sh" install
```

That writes `CREWFORGE5_ROOT` into `settings.json`'s `env` block, which is in
the environment of both the Bash tool and every hook subprocess. `--project DIR`
scopes it to one repo instead of the user config; `report` shows what is set
without writing; `uninstall` removes only the keys it added.

**Exporting it by hand does not work, and cannot.** Shell state does not survive
a single tool call, so an `export` reaches the end of its own command and no
further. Call sites therefore never fall back to `.` (which resolves to the wrong
tree once the plugin lives anywhere but the repo you are standing in): the flow
driver locates the plugin from its own path, and the commands use the
harness-expanded `${CLAUDE_PLUGIN_ROOT}`. A test fails if the fallback returns.

## The hooks act only in CrewForge5 projects

Every hook CrewForge5 ships is inert unless the project has `.crewforge5.toml`
(the first `/crewforge5:plan new` writes it), and `[hooks] enabled = false`
there turns them all off:

| Hook | Event | What it does |
| --- | --- | --- |
| `pre-edit` | `PreToolUse(Edit\|Write\|MultiEdit)` | **Denies** edits under `[build] protected_paths`, and to test files (`[build] test_globs`) while `build fix on` |
| `post-edit` | `PostToolUse(Edit\|Write\|MultiEdit)` | Says when the edited file is missing from the accepted plan.md's Files that change |
| `bash-guard` | `PreToolUse(Bash)` | **Denies** `git add -A`, `git add .`, and `find` from `/` or `~`; heredoc bodies and quoted prose never match |
| `learn-capture` | `PostToolUse(Bash)` | Appends a ledger line when a skill's own script reports a failure |
| `learn-nudge` | `SessionStart` | One line when the ledger has ≥5 undistilled entries |
| session start | `SessionStart` | Merges `[workflows.env]` (see [The verdict CLI](#the-verdict-cli)) |

`pre-edit` and `post-edit` run `scripts/hook.py` through `uv run --offline
--no-project`; like every hook but session start they finish within 10 s, and
none installs anything or reaches the network. The old opt-in,
`CREWFORGE5_HOOKS=1` (written by `env_install.sh --hooks`), is retired: `--hooks`
is accepted and ignored, and `install` removes a leftover `=1`. Hooks are
spawned by the harness, so a session `export` never reaches them; to switch
them off by environment, put `CREWFORGE5_HOOKS=off` in `settings.json`'s `env`
block.

`sprint-watchdog-guard` is always registered but inert: it does nothing until a
sprint arms it with an activation file in the repo, and goes inert again at
teardown.

## Dependencies

**Required:** `bash`, `git`, `python3`, `jq`. Four scripts hard-require `jq`
(`crew_check.sh`, `coverage_check.sh`, `detect_language.sh`,
`preflight_subskills.sh`) — it is a base dependency, not an optional extra.

**Optional, and degrade visibly when absent:** `rtk`, `just`, `repomix`,
`shellcheck`, `bats`, `graphify`, `codegraph`. Absent tooling is reported by
name; nothing fails silently. `graphify` is not shipped as a skill — it needs a
`uv`-installed binary, and a plugin that hard-fails on a missing external tool
is a bad first impression.

`/crewforge5:init` checks this list before it does anything else, and it is the
one check that answers on a machine without `jq` — every other gate, and the
flow driver itself, exits early there, so reaching them first would report one
missing tool and hide the rest:

```bash
bash "$CREWFORGE5_ROOT/skills/init/scripts/init_gate.sh" deps
```

A missing required tool stops the run: init offers to install what needs no
`sudo`, hands you a copy-paste block for anything else, and waits — re-checking
and re-listing until every required tool is there. Optional tools missing are
named and carried.

## State

Nothing is written to your `CLAUDE.md`, ever. Runtime state lands in
`${XDG_STATE_HOME:-~/.local/state}/crewforge5/` (or `$CLAUDE_PLUGIN_DATA` where
the harness provides it). No `ceilings.json` is shipped — the budgets in one are
byte sizes of one machine's files, so it is generated on first `record`.
`team-sprint.config.yaml` is machine-local too; copy
`skills/team-sprint/team-sprint.config.yaml.example` if you want to change a
default.

## The verdict CLI

The gate layer is moving to a Python 3.11 standard-library CLI, following
`docs/specs/cc-sdlc-alignment.md` in the repository. `/crewforge5:plan`,
`/crewforge5:design`, `/crewforge5:build` and `/crewforge5:review` run on it;
`init` and `execute` are still bash flows:

```bash
uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" <stage> <action> [arg] [--slug <slug>]
```

Each call prints one JSON verdict with `ok`, `next`, and `reason` when `ok` is
false. Act on `ok`, quote `reason` word for word, follow `next`
(`templates/command-preamble.md` is the preamble every command opens with).
Stages: `plan` writes `intent.md`, `design` writes `spec.md`, `build` writes
`plan.md`, each with `new | check | accept`, and `status` lists every feature.
Artifacts live in `crewforge5/<slug>/`. `check` validates the required sections
and the `Status:` and `Risk:` lines. Each `new` is refused until a human has
accepted the previous artifact, and `accept` sets `Status: accepted`. Only a
human accepts: the command asks through AskUserQuestion before it runs `accept`.
`build check` also refuses an Order-of-work step that names no failing test, and
a `Risk: high` plan without a `Tech lead: <name>` line under Risks.

**Build.** After `build accept`, `build red <n>` runs `[commands] test` and
succeeds only when it fails; `build green <n>` succeeds only when it passes after
a red for the same Order-of-work step. Each success appends `{step, phase, sha,
ts, exit}` to `crewforge5/<slug>/tdd.jsonl`, and a step is done only with a red
then a green. `build sync` lists every file changed since the plan was accepted
(committed or not) that plan.md's Files that change does not name: add it there
in the same commit, or revert it. `build fix on|off` is bug-fix mode, in which
the `pre-edit` hook denies edits to test files. `crewforge5/<slug>/build-state.json`
holds the acceptance commit and fix mode. `/crewforge5:execute` on an accepted
plan.md is the shortcut for `/crewforge5:build implement` then `/crewforge5:review
run` and `review`, and prints the commands it ran.

**Review.** `review run` is refused until every Order-of-work step has a
red→green pair in `tdd.jsonl`; it then runs `[commands] test`, `lint` and
`build` and writes `crewforge5/<slug>/test-report.json`, and the command spawns
the read-only `verifier` agent (sonnet, fresh context) against plan.md's Proof.
`review review` needs that report passing at HEAD, then validates
`crewforge5/<slug>/review.md`: `## Bugs`, `## Security` and `## Compliance`
(the passes in `templates/REVIEW.md`), each finding a bullet starting
`Important:` or `Nit:` with `path:line`, at most five nits. It is a checkpoint
boundary. `review evals` runs every `evals/*.json` through `claude -p` and fails
under `[evals] threshold`; `templates/agent-evals.yml` runs it in CI.

Config lives in `.crewforge5.toml` (the first `new` writes it from
`templates/crewforge5.toml`). It is deep-merged over the defaults:
`[project] home` (the feature folder, default `crewforge5`, or set
`CREWFORGE5_HOME`), `[commands] test` (what `build red|green` run; `review
run` adds `lint` and `build`), `[evals] threshold`,
`[build] require_adversarial_stamp` (when true, `build check` needs the
planner's `adversarial-review: status=clean|user-override` stamp in `plan.md`),
`[build] protected_paths` and `test_globs` (read by the `pre-edit` hook), and
`[hooks] enabled`.

**Checkpoints.** Each `accept`, and `review review`, commits only the plugin's
output, which is the home directory plus `[checkpoint] paths`. The commit subject
is `<stage>(<slug>): <action> — <artifact>`, with `(+N files)` when other files are
included. The commit uses a pathspec, so it never stages source or tests, and
work you have already staged stays staged. It is skipped during a merge or
rebase, or when nothing changed. A failed commit is reported under `checkpoint`
and never blocks the stage.

Every layer has one off switch in config and one environment variable:

| Layer | Config | Environment |
| --- | --- | --- |
| Checkpoint commits | `[checkpoint] enabled = false` | `CREWFORGE5_CHECKPOINT=off` |
| Stage workflows | `[workflows] enabled = false` (`auto_env = false` stops only the env merge) | `CREWFORGE5_WORKFLOWS=off` |
| Hooks | `[hooks] enabled = false` | `CREWFORGE5_HOOKS=off` (in `settings.json`'s `env` block) |

**Workflows.** Each planning command runs one read-only Workflow script from
`workflows/`, as `crewforge5:<name>`: `intent-scout` (plan), `design-panel`
(design), `plan-critic` (build) and `review` (review: Bugs, Security and
Compliance passes against `REVIEW.md` with the architecture and cross-boundary
lenses of the retired `architect-reviewer` and `boundary-reviewer` agents folded
in, two skeptics per finding, at most five nits; its inline fallback is the
read-only `reviewer` agent, opus). `build implement` runs `story-executor`
over a wave of independent steps: one agent per step in its own git worktree,
writing only there and returning a branch with a test commit and a change
commit, which the command applies step by step around `build red` and `build
green`. Every finding goes to a skeptic, and an
optional `pack` argument is read as data, never instructions. The planning
workflows are read-only and advisory: the command writes the artifact and the
CLI still decides. `crewforge5
workflows list` reads the catalog from each script's `meta` and says whether the
layer is on; when it is off, or the Workflow tool is missing, every step has an
inline fallback. Plugin settings cannot set env, so a `SessionStart` hook
(`scripts/hook.py`, through `uv run --no-project`) runs `crewforge5 workflows
env` in projects that have `.crewforge5.toml`, and only there: it merges
`[workflows.env]` (default `CLAUDE_CODE_WORKFLOWS=1`; any key outside
`CLAUDE_CODE_WORKFLOW*` is refused) into `.claude/settings.local.json` without
overwriting a value already set, and appends `export` lines to
`CLAUDE_ENV_FILE`. The Workflow tool sees it from the next session.
`disableWorkflows` in Claude Code settings still wins.

## Rules

Several skills cite house rules — the recon escalation ladder, verification
discipline, git hygiene, the subagent delivery contract. Those ship as files in
`rules/`, and they are installed by an explicit command, never written into your
`CLAUDE.md` by a plugin:

```bash
bash "$CREWFORGE5_ROOT/scripts/sprint_init.sh" report      # what exists, what conflicts
bash "$CREWFORGE5_ROOT/scripts/sprint_init.sh" install     # symlink into .claude/rules/
bash "$CREWFORGE5_ROOT/scripts/sprint_init.sh" uninstall   # remove the links
```

`/crewforge5:rules-install` is the same installer as a slash command — it runs
`report` first and refuses to resolve a conflict by overwriting. It is a
utility, not a workflow stage: the entry points above remain the whole
planning-and-execution surface.

`report` reads your existing `CLAUDE.md` and rules and names contradictions
before anything is linked — a rule of yours saying "stage with `git add -A`"
against `bash-guard`'s denial of exactly that, for instance.

## Trimming your CLAUDE.md safely

`context-hygiene` will help you cut a bloated `CLAUDE.md`, but a trim is judged
by how much shorter it got — and the lines costing the most tokens are usually
the ones worth keeping. Check any proposal before you apply it:

```bash
bash "$CREWFORGE5_ROOT/scripts/retention_gate.sh" CLAUDE.md proposed.md
```

It fails if any `never`/`always`/`must` line, backticked command, path, pinned
version or quoted error string stopped appearing anywhere in the proposal.
Reorganising passes; losing does not. It reads two files and prints a verdict —
it cannot edit anything, so applying stays your decision.

## Tests

The installed package is this `plugin/` directory only. The tests, CI, the
release gates' probes and the dev tooling live at the repository root and do not
ship; the repository's root `README.md` lists them and `CLAUDE.md` says how to
run them (`just check`).

## Support

This is a large plugin and it invites issues. If that turns out to be more than
can be carried, the honest alternative is a starter-config repo you fork — far
less machinery, no maintenance promise.

## Credits

Not all of this was written here. Five of the shipped skills started as someone
else's work and were adapted; four external projects are driven rather than
vendored. Both lists are below, because a skill you can read is a skill whose
origin you should be able to check.

**Adapted skills.** Each row was matched against the upstream file, not
guessed — a verbatim frontmatter description, a distinctive trigger token, or an
install line still present in the vendored copy.

| Skill | Upstream | Owner | Licence |
| --- | --- | --- | --- |
| `skills/adhd` | [UditAkhourii/adhd](https://github.com/UditAkhourii/adhd) | UditAkhourii | MIT |
| `skills/grill-me` | [mattpocock/skills](https://github.com/mattpocock/skills) — `productivity/grilling` | Matt Pocock | MIT |
| `skills/drawio` | [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp) — `plugins/claude-code/skills/drawio` | JGraph Ltd (draw.io) | Apache-2.0 |
| `skills/playwright-cli` | [microsoft/playwright](https://github.com/microsoft/playwright) — `packages/playwright-core/src/tools/skills/playwright-cli` | Microsoft | Apache-2.0 |
| `skills/tech-debt-audit` | [ksimback/tech-debt-skill](https://github.com/ksimback/tech-debt-skill) | ksimback | **none declared** |

`tech-debt-skill` ships no `LICENSE`, so its redistribution terms are unstated.
It is credited here on that basis, and would be the first thing to remove if the
author asked.

`skills/adhd` links its own upstream in `references/companion.md` — the skill is
this repo's in-Claude implementation of a spec whose prose lives there, and the
companion `adhd-agent` CLI is the author's.

**External projects the skills drive.** These are installed by you, not shipped
here, and each degrades visibly when absent (see [Dependencies](#dependencies)).

| Tool | Project | Owner | Licence | Used by |
| --- | --- | --- | --- | --- |
| `repomix` | [yamadashy/repomix](https://github.com/yamadashy/repomix) | yamadashy | MIT | `use-repo-code`, the recon ladder |
| `graphify` (`graphifyy` on PyPI) | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | Graphify-Labs | Apache-2.0 | `team-sprint` Phase 0/2/4 recon |
| `drawio` desktop CLI, `drawio-mcp` | [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp) | JGraph Ltd | Apache-2.0 | `drawio` export and live-viewer paths |
| `playwright-cli` | [microsoft/playwright](https://github.com/microsoft/playwright) | Microsoft | Apache-2.0 | `playwright-cli`, `ac-validate` |

Everything else under `skills/`, `agents/`, `hooks/` and `scripts/` is original
to this repo.

## License

MIT. See [LICENSE](LICENSE).
