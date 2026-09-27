---
description: Stage 3 Build — accepted spec.md to a test-first plan.md; a human accepts it
argument-hint: new | check | accept | status  [--slug <slug>]
allowed-tools: Bash(uv run *), Bash(git *), Read, Edit, Write, Glob, Grep, AskUserQuestion, Agent, Workflow
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control.

Workflows: when `crewforge5 workflows list` reports `enabled: true` and the Workflow tool is available, run the step's workflow as `Workflow({name: "crewforge5:<name>", args: {...}})`; otherwise do the step's inline fallback. Workflows are read-only and advisory: you write the artifact from the result, and the Python gate decides either way. The session-start hook sets `CLAUDE_CODE_WORKFLOWS=1` in `.claude/settings.local.json` (`crewforge5 workflows env` does the same on demand).

Arguments: $ARGUMENTS

## new  (plan mode: read and reason; edit nothing but plan.md)
1. `crewforge5 build new` (refused until spec.md is accepted) writes `crewforge5/<slug>/plan.md`.
2. Read intent.md, spec.md, CLAUDE.md and the files the spec names. Fill plan.md:
   - Files that change: one path per line, `(new)` where created.
   - Order of work: numbered steps, each one story: one behaviour, committable green on its own, observable acceptance criteria, and the failing test written first (`1. <behaviour> — test: <path>::<name> fails first`). `check` refuses a step that names no test.
   - Risks: what could break, the riskiest step (put it early), options rejected (design's `rejected`); `Tech lead: <name>` when `Risk: high`.
   - Proof: the commands and their expected output.
3. Critique: run `crewforge5:plan-critic` with `{slug}`: blast radius, test-first, ordering and spec coverage, a skeptic per finding; it returns confirmed `issues`, each with its plan.md edit. Apply or explicitly reject each one. Inline fallback: put the plan through those four lenses yourself, one Agent per lens when it helps. Iterate until an engineer who never saw this conversation could implement from plan.md alone.
4. `crewforge5 build check` until `ok`.

## check
`crewforge5 build check` and report the verdict.

## accept
Only a human accepts. Ask (AskUserQuestion) the engineer, or the named tech lead for `Risk: high`, to accept plan.md. On yes run `crewforge5 build accept`, which commits `build(<slug>): accept — plan.md`. Implementation (red/green/sync/fix) arrives in a later release; until then follow the verdict's `next`.

## status
`crewforge5 status --slug <slug>` and report `next` verbatim.
