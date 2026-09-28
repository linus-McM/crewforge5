# CrewForge5

Agents and skills are a resource with a cost. This plugin generates them where
they belong, executes work with them, and stops them rotting.

```
/crewforge5:init    → measure and audit the config you already have into audit.md; a human accepts the edits
/crewforge5:crew    → survey the stack and forge a validated per-language agent crew
/crewforge5:plan    → a goal becomes crewforge5/<slug>/intent.md, accepted by a human
/crewforge5:design  → the accepted intent becomes spec.md, accepted by a human
/crewforge5:build   → the accepted spec becomes a test-first plan.md, accepted by a human
/crewforge5:review  → the implemented plan is checked, reviewed against REVIEW.md and checkpointed
/crewforge5:execute → the shortcut: build implement then review on an accepted plan.md
```

That is the whole surface. Everything underneath — the crew agents, the review
workflow, the recon tooling, the distillation pass — is a hidden skill, a
workflow or a template one of them names when its step needs it.

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
| `/crewforge5:init` | Config hygiene: `new` measures a config root and writes `crewforge5/init-<date>/audit.md`, `check`, `accept` applies the human-approved slimming and rectify edits, re-measures and commits (`new | check | accept | status`) | "clean up my Claude config", "audit context load", "rightsize the environment" |
| `/crewforge5:crew` | The crew factory: `survey` the stack, `forge <lang>` a graded agent crew, `validate` and `status` it | "build the agent crew", "onboard a language" |
| `/crewforge5:plan` | Stage 1: interview the originator into `intent.md` (`new "<title>" | check | accept | status`) | "plan this feature" |
| `/crewforge5:design` | Stage 2: the accepted intent becomes `spec.md` with Concerns and a Requirements trace | "design this feature" |
| `/crewforge5:build` | Stage 3: plan mode against the accepted spec writes `plan.md`, every step naming its failing test | "write the build plan" |
| `/crewforge5:review` | Stage 4: `run` (test/lint/build into `test-report.json`, refused without red→green evidence), `review` (`review.md` from the review workflow, committed), `evals` | "review this feature" |
| `/crewforge5:execute` | On an accepted `plan.md`, the shortcut for `build implement` then `review run` and `review review`, then distilled learnings; prints the commands it ran. `--teams` runs the hidden graph-mode agent-team sprint instead | "run a sprint", "execute this plan" |

All eight are slash commands over the verdict CLI (below); there is no flow
skill and no flow driver any more (spec phase 8). A feature's progress is read
from its artifacts on disk: `crewforge5 status` lists every feature under
`crewforge5/<slug>/`, which of `intent.md`, `spec.md` and `plan.md` are accepted,
present or missing, and the one command to run next. Execution state that is not
an artifact (the acceptance commit, fix mode) lives in
`crewforge5/<slug>/build-state.json`, owned by the CLI.

**Coming from 0.x?** `crewforge5 migrate` moves each old run into the feature
home once: a `.crewforge5/<flow>/<subject>/` flow run lands in
`crewforge5/<subject>/migrated/<flow>/`, a `docs/plans/<name>.md` plan (with its
`<name>-review/` directory) in `crewforge5/<name>/migrated/`. It refuses to
overwrite anything, records what it moved in `migrated/MIGRATED.json`, and a
second call is a no-op. Nothing writes `.crewforge5/` or `docs/plans/` any more.

### The Teams path (the one open D3 item)

`/crewforge5:execute --teams` runs the hidden `team-sprint` skill: the accepted
`plan.md` becomes a story plan (`sprint-<slug>.md` beside it, one story per
Order-of-work step, the human acceptance as its provenance line), and an agent
team drives the stories in parallel graph-mode waves, each in its own git
worktree, to a merged commit with its own coverage, AC/DoD and review-fleet
gates. Its sprint state lives in `.team-sprint/sprints/`, the one run directory
outside the feature home. It writes no `tdd.jsonl`, so `review run` refuses a
feature it built. It stays only until one real sprint has been measured both
ways against `build implement`'s Workflow fan-out (spec decision D3); then it is
removed.

### Which command uses which skill

Every skill is hidden (`disable-model-invocation: true`): a command or agent
names it by path, and it costs nothing until then.

| Skill | Used by | For |
| --- | --- | --- |
| `token-slim` | `/crewforge5:init` | `init new` and `accept` measure with its `baseline.py`; the Proposed edits' trims |
| `context-hygiene` | `/crewforge5:init` | `init new`'s audit passes (the `config-audit` fallback) |
| `skill-validator` | `/crewforge5:init`, `/crewforge5:crew` | `init new`, `init accept` and `crew validate` grade through its scripts |
| `agent-validator` | `/crewforge5:init`, `/crewforge5:crew` | same; `crew-factory` grades every generated agent to A |
| `skill-rectifier` | `/crewforge5:init` | the skill fixes `init accept` applies |
| `agent-rectifier` | `/crewforge5:init`, `/crewforge5:crew` | the agent fixes; the validator↔rectifier loop |
| `archify` | `/crewforge5:plan`, `design`, `build`, `review` | the stage documents' `## docs` step |
| `graphify` | every command | the knowledge graph behind `crewforge5 knowledge` and `graphify query` |
| `self-improve` | `/crewforge5:execute` | distilling the ledger after a run |
| `team-sprint` | `/crewforge5:execute --teams` | the graph-mode agent-team sprint (D3) |
| `ac-validate` | `team-sprint`, generated crews | UI acceptance checks, assigned by `crew-factory` |
| `playwright-cli` | `ac-validate` | frontend AC verification |
| `plugin-forge` | — | reachable by name only |

What used to be flow skills is now a template the commands read:
`templates/interview.md` (the diverge frames and the grilling rules of
`plan new`), `templates/concerns.md` (the tech-debt dimensions of `design new`),
`templates/adversarial-stamp.md` (the optional plan stamp), `templates/house-rules.md`
(the config house rules of `init new`) and `templates/repomix-flags.md` (the
pack flags of the recon ladder).

## What it costs you

Skill and agent descriptions load into **every** session whether or not you use
them. That is the plugin's rent, and it is measured rather than asserted:

```bash
bash "$CREWFORGE5_ROOT/scripts/budget_check.sh" --verbose
```

The bundle is **~381 tokens** always-loaded across 13 catalogue entries, against
a budget of **450** — one description's worth of headroom, so rewording a
trigger phrase does not turn the build red, while a whole new listed surface
still cannot slip in unpriced. All **13 skills** carry
`disable-model-invocation: true`, so they cost nothing until a command names one
or you call it by name. That discipline is the only reason a bundle this size is
affordable, and `budget_check.sh` fails the build over the budget rather than
moving it.

Cost is only half of what the gate asserts. It also checks *which* entries are
listed: no skill, and exactly the `init`, `crew`, `plan`, `design`, `build`,
`review`, `execute` and `rules-install` commands. An extra entry point with a short description used
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
tree once the plugin lives anywhere but the repo you are standing in): scripts
locate the plugin from their own path, and the commands use the
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

## Dependencies

**Required:** `bash`, `git`, `python3`, `jq`. Four scripts hard-require `jq`
(`crew_check.sh`, `coverage_check.sh`, `detect_language.sh`,
`preflight_subskills.sh`) — it is a base dependency, not an optional extra.

**Optional, and degrade visibly when absent:** `rtk`, `just`, `repomix`,
`shellcheck`, `bats`, `graphify`, `codegraph`. Absent tooling is reported by
name; nothing fails silently. `graphify` is not shipped as a skill — it needs a
`uv`-installed binary, and a plugin that hard-fails on a missing external tool
is a bad first impression.

`crewforge5 knowledge bootstrap`, which every command runs first, names each
missing tool once; nothing is installed unless `[knowledge] auto_install = true`.

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
`/crewforge5:design`, `/crewforge5:build`, `/crewforge5:review`, `/crewforge5:init`
`/crewforge5:crew` and `/crewforge5:execute` run on it:

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
run` and `review`, and prints the commands it ran. `crewforge5 migrate [<source>]
[--slug s]` moves a 0.x run into the feature home (above).

**Init.** `init new [<config root>]` (default `[init] target`, else `.claude/`,
else the project) measures the root through the scripts the skills ship —
token-slim's `baseline.py`, the skill and agent validators graded by `grade.sh` —
plus CLAUDE.md, rules, hooks and MCP servers, writes the before-picture to
`crewforge5/init-<date>/measure.json` and renders `audit.md` (Baseline, Findings,
Proposed edits, Retention, Open questions). The command fills it from the
read-only `config-audit` workflow. `init check` validates it; `init accept`,
after a human picks which edits to apply, runs `retention_gate.sh` over every
changed instruction file, re-measures, refuses if validator failures rose,
appends the Result and commits `init(<slug>): accept — audit.md`. The config
edits themselves are left for you to commit, as `next` says.

**Crew.** `crew survey` detects the language (`[project] language`, else
`detect_language.sh`); `crew validate [<lang>]` runs `crew_check.sh check`,
re-grades each generated agent and checks `.claude/crews/<lang>.json`'s
`validation` grades (grade A passes), then copies the manifest's `test`, `lint`
and `build` commands into `.crewforge5.toml`'s `[commands]` where those are still
empty (`.crewforge5.toml` is the only config, spec R-C1); `crew status [<lang>]`
reports them. With
`[build] require_crew = true` (off by default), `build accept` is refused until
the plan's language has a passing crew, and `next` is `/crewforge5:crew forge
<lang>`.

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
`CREWFORGE5_HOME`), `[project] language` (the crew language; empty lets
`detect_language.sh` decide), `[init] target`, `[build] require_crew`, `[commands] test` (what `build red|green` run; `review
run` adds `lint` and `build`), `[evals] threshold`,
`[build] require_adversarial_stamp` (when true, `build check` needs the
`adversarial-review: status=clean|user-override` stamp `templates/adversarial-stamp.md`
describes in `plan.md`),
`[build] protected_paths` and `test_globs` (read by the `pre-edit` hook),
`[hooks] enabled`, and `[interop] sdlc_home` (cc_sdlc's feature home, below).

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
| Knowledge (graph + bundle) | `[knowledge] enabled = false` (also turns packs off) | `CREWFORGE5_KNOWLEDGE=off` |
| Context packs and their gates | `[packs] enabled = false` | `CREWFORGE5_PACKS=off` |
| Stage documents and their gates | `[docs] enabled = false` (`open = false` stops only the opener) | `CREWFORGE5_DOCS=off` |

**Knowledge.** Every command opens with `crewforge5 knowledge bootstrap`
(idempotent; `bootstrap check` writes nothing). It is check-only unless
`[knowledge] auto_install = true`: it writes `.graphifyignore`, builds
`graphify-out/graph.json` when `graphify` is on PATH and the OKF bundle
(`index.md`, `features/`, `modules/`), but installs uv, Graphify
(`uv tool install graphifyy`), Repomix and Archify only with the opt-in, and
otherwise names each missing tool. The command then reads the bundle's
`index.md` before raw files and asks `graphify query` / `graphify affected`
before grep. When cc_sdlc's `sdlc/knowledge/` exists the bundle is shared
(spec D2): CrewForge5 writes only its own `features/` concepts and the
Features block of that index; otherwise it lives in `crewforge5/knowledge/`.
`knowledge status` says how far the graph and bundle are behind HEAD
(`[knowledge] max_behind`), `refresh` rebuilds them and `check` validates
OKF conformance. Graphify, uv and npm are subprocesses; nothing is installed
from a hook.

**Context packs.** `crewforge5 knowledge pack <stage> [--slug s]
[--max-tokens N]` writes a commit-pinned Repomix pack plus manifest to
`graphify-out/packs/<slug>/` (git-ignored, never committed). Seeds come from
the stage artifact (plan: the backticked paths in intent.md's Affected users
and systems; design: those plus spec.md's Design; build: plan.md's Files that
change; review: `git diff <[packs] base>...HEAD`), grown `[packs] hops` call
edges plus each seed's community. A frozen exclude list (`.env*`,
`.claude/settings.local.json`, keys and certificates, `.netrc`/`.npmrc`/`.pypirc`,
`*credentials*`, `graphify-out/`, untracked, symlinked and git-ignored files),
a Bandit scan of the Python files (`uv tool run --from bandit==1.9.4`) that
fails closed, and Repomix's secret check, forced on by
`templates/knowledge/repomix.config.json`, keep secrets out; verdicts name
paths and rule ids, never the matched text. The command passes the pack's
`path` to the stage workflow as `args.pack`. `build accept` needs a build pack
at HEAD and `review review` a review pack at HEAD accounting for every changed
text file; plan and design packs are advisory. Missing Repomix
(`npm i -g repomix`) skips an advisory pack and refuses a gated one.

**Stage documents.** Each stage ends with an Archify diagram under
`crewforge5/<slug>/docs/` (plan `architecture`, design `dataflow`, build
`workflow`, review `sequence`), authored as `<stage>.json` by
`templates/docs-step.md`, delivered by `crewforge5 docs render <stage>` with a
receipt of source digests (the `Status:` line masked), checked by `docs check`
and shown by `docs open` (never under `CI`). `plan|design|build accept` and
`review review` are refused while the document is missing or stale. Without
Node >= 18 or the Archify skill (`npx -y skills add tt-a1i/archify --skill
archify --agent claude-code --global --copy --yes`) the step is skipped, not
failed. Documents are never rendered from a hook. This replaces the draw.io
integration diagram execute ran as phase 8.

**Workflows.** Each planning command runs one read-only Workflow script from
`workflows/`, as `crewforge5:<name>`: `config-audit` (init: CLAUDE.md and
rules, hooks, MCP, skills and agents lenses), `intent-scout` (plan), `design-panel`
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

## Working with cc_sdlc

CrewForge5 and [cc_sdlc](https://github.com/linus-McM/cc_sdlc) share one artifact
format, so either can take a feature from the other (spec R-X1, R-X2).

**cc_sdlc plans, CrewForge5 builds.** When cc_sdlc has accepted
`sdlc/<slug>/spec.md`, `/crewforge5:build new --from-sdlc <slug>` (CLI:
`crewforge5 build new --from-sdlc <slug>`) copies its `intent.md` and `spec.md`
into `crewforge5/<slug>/`, replacing the metadata line with
`From: sdlc/<slug>/spec.md (accepted). Status: accepted. Risk: <risk>.`, and
writes `plan.md`. It is refused while either file is missing, not accepted, or
missing a required section, and it never overwrites a CrewForge5 feature of the
same name. cc_sdlc's home is `sdlc/` (`[interop] sdlc_home`, or `SDLC_HOME` as
cc_sdlc reads it). The rest of the build stage, and `review`, run as usual.

**CrewForge5 builds, cc_sdlc tests and deploys.** The artifact names
(`intent.md`, `spec.md`, `plan.md`, `tdd.jsonl`, `test-report.json`,
`review.md`) and the required sections of each template are cc_sdlc's, and
`tdd.jsonl` rows and `test-report.json` carry cc_sdlc's keys (CrewForge5 adds
`sha`). `tests/test_interop.py` pins them to a vendored copy of cc_sdlc's
section lists, so the formats cannot drift. Pointing cc_sdlc's `test` and
`deploy` stages at a CrewForge5 feature folder is a setting on the cc_sdlc side:

```toml
# .sdlc.toml
[sdlc]
home = "crewforge5"   # read crewforge5/<slug>/ instead of sdlc/<slug>/
```

That key is a follow-up in the cc_sdlc repository (today cc_sdlc reads only
`SDLC_HOME`, so `SDLC_HOME=crewforge5` works in the meantime); nothing here
changes when it lands.

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

Not all of this was written here. Four of the shipped skills and templates started as someone
else's work and were adapted; four external projects are driven rather than
vendored. Both lists are below, because a skill you can read is a skill whose
origin you should be able to check.

**Adapted skills.** Each row was matched against the upstream file, not
guessed — a verbatim frontmatter description, a distinctive trigger token, or an
install line still present in the vendored copy.

| Skill | Upstream | Owner | Licence |
| --- | --- | --- | --- |
| `templates/interview.md` (diverge frames; was the adhd skill) | [UditAkhourii/adhd](https://github.com/UditAkhourii/adhd) | UditAkhourii | MIT |
| `templates/interview.md` (grilling; was the grill-me skill) | [mattpocock/skills](https://github.com/mattpocock/skills) — `productivity/grilling` | Matt Pocock | MIT |
| `skills/playwright-cli` | [microsoft/playwright](https://github.com/microsoft/playwright) — `packages/playwright-core/src/tools/skills/playwright-cli` | Microsoft | Apache-2.0 |
| `templates/concerns.md` (was the tech-debt-audit skill) | [ksimback/tech-debt-skill](https://github.com/ksimback/tech-debt-skill) | ksimback | **none declared** |

`tech-debt-skill` ships no `LICENSE`, so its redistribution terms are unstated.
It is credited here on that basis, and would be the first thing to remove if the
author asked.

The diverge frames are this repo's in-Claude adaptation of the adhd spec, whose
prose and companion `adhd-agent` CLI are the author's.

**External projects the skills drive.** These are installed by you, not shipped
here, and each degrades visibly when absent (see [Dependencies](#dependencies)).

| Tool | Project | Owner | Licence | Used by |
| --- | --- | --- | --- | --- |
| `repomix` | [yamadashy/repomix](https://github.com/yamadashy/repomix) | yamadashy | MIT | `templates/repomix-flags.md`, the recon ladder, `crewforge5 knowledge pack` |
| `graphify` (`graphifyy` on PyPI) | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) | Graphify-Labs | Apache-2.0 | `team-sprint` Phase 0/2/4 recon, the knowledge layer |
| `archify` (a Claude skill, `npx -y skills add tt-a1i/archify`) | [tt-a1i/archify](https://github.com/tt-a1i/archify) | tt-a1i | see upstream | `crewforge5 docs render|check|open` |
| `bandit` (via `uv tool run`) | [PyCQA/bandit](https://github.com/PyCQA/bandit) | PyCQA | Apache-2.0 | the context-pack secret scan |
| `playwright-cli` | [microsoft/playwright](https://github.com/microsoft/playwright) | Microsoft | Apache-2.0 | `playwright-cli`, `ac-validate` |

Everything else under `skills/`, `agents/`, `hooks/` and `scripts/` is original
to this repo.

## License

MIT. See [LICENSE](LICENSE).
