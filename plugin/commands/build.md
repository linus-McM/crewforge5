---
description: Stage 3 Build — accepted spec.md to a test-first plan.md; a human accepts it
argument-hint: new | check | accept | implement | red <step> | green <step> | sync | fix on|off | status  [--slug <slug>]
allowed-tools: Bash(uv run *), Bash(git *), Read, Edit, Write, Glob, Grep, AskUserQuestion, Agent, Skill, Workflow
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control.

Workflows: when `crewforge5 workflows list` reports `enabled: true` and the Workflow tool is available, run the step's workflow as `Workflow({name: "crewforge5:<name>", args: {...}})`; otherwise do its inline fallback. The Python gate decides either way. The session-start hook sets `CLAUDE_CODE_WORKFLOWS=1` in `.claude/settings.local.json`. If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook.

Arguments: $ARGUMENTS

## new  (plan mode: read and reason; edit nothing but plan.md)
1. `crewforge5 build new` (refused until spec.md is accepted) writes `crewforge5/<slug>/plan.md`.
2. Read intent.md, spec.md, CLAUDE.md and the files the spec names. Fill plan.md:
   - Files that change: one path per line, `(new)` where created.
   - Order of work: numbered steps, each one story: one behaviour, committable green on its own, observable acceptance criteria, and the failing test written first (`1. <behaviour> — test: <path>::<name> fails first`). `check` refuses a step that names no test.
   - Risks: what could break, the riskiest step (put it early), options rejected; `Tech lead: <name>` when `Risk: high`.
   - Proof: the commands and their expected output.
3. Critique: run `crewforge5:plan-critic` with `{slug}` (blast radius, test-first, ordering, spec coverage, cross-boundary; a skeptic per finding). Apply or explicitly reject each confirmed issue. Inline fallback: put the plan through those five lenses yourself, one Agent per lens when it helps. Iterate until an engineer who never saw this conversation could implement from plan.md alone.
4. `crewforge5 build check` until `ok`.

## check
`crewforge5 build check` and report the verdict.

## accept
Only a human accepts. Ask (AskUserQuestion) the engineer, or the named tech lead for `Risk: high`, to accept plan.md. On yes run `crewforge5 build accept`, which commits `build(<slug>): accept — plan.md`.

## implement  (after accept; set `[commands] test` in `.crewforge5.toml`)
Per Order-of-work step: write only its failing test; `crewforge5 build red <n>` must be `ok` (if the tests pass, the test is wrong or the behaviour exists: stop and say so); make the smallest change; `crewforge5 build green <n>`; `crewforge5 build sync` (list each `unplanned` file in plan.md in the same commit, or revert it); commit `build(<slug>): <step>`. A step is done only when red then green report `ok`.
Parallel: group steps with disjoint files into waves and run `crewforge5:story-executor` with `{slug, steps: [n...], developer: <crew developer agent, if any>}`: one worktree agent per step returns a branch with a test commit and a change commit. Per step, in order: `git cherry-pick -n <test_commit>`, `build red <n>`, `git cherry-pick -n <commit>`, `build green <n>`, `build sync`, commit; delete the branch. Inline fallback: do the steps one by one as above.
When every step is green run `/simplify`, then `crewforge5 build sync` once more. Next: `/crewforge5:review run`.

## fix on | fix off
Bug-fix mode: reproduce the bug as a failing test and commit it, `crewforge5 build fix on` (the pre-edit hook then denies edits to test files), make it pass, `crewforge5 build fix off`.

## red | green | sync
Run the named `crewforge5 build` mechanic directly and report the verdict.

## status
`crewforge5 status --slug <slug>` and report `next` verbatim.
