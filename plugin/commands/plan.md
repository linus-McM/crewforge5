---
description: Stage 1 Plan — interview the originator into intent.md; a human accepts it
argument-hint: new "<title>" | check | accept | status  [--slug <slug>]
allowed-tools: Bash(uv run *), Bash(git *), Read, Edit, Write, Glob, Grep, AskUserQuestion, Workflow
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control.

Workflows: when `crewforge5 workflows list` reports `enabled: true` and the Workflow tool is available, run the step's workflow as `Workflow({name: "crewforge5:<name>", args: {...}})`; otherwise do the step's inline fallback. Workflows are read-only and advisory: you write the artifact from the result, and the Python gate decides either way. The session-start hook sets `CLAUDE_CODE_WORKFLOWS=1` in `.claude/settings.local.json` (`crewforge5 workflows env` does the same on demand).

Arguments: $ARGUMENTS

## new "<title>"
1. `crewforge5 plan new "<title>"` creates `crewforge5/<slug>/intent.md` from the template (and `.crewforge5.toml` if missing).
2. Scout: run `crewforge5:intent-scout` with `{slug, title}`: systems, users, risk triggers, prior art and divergent framings, a skeptic per finding, then section drafts and an `interview` list. Inline fallback: read CLAUDE.md and grep for the same five things yourself, citing path:line. Drafts are hypotheses, not answers.
3. Diverge: before asking anything, frame the goal at least three ways (the literal ask, the smallest version that helps, the version that removes the underlying problem) and note what each leaves out.
4. Grill: interview the originator one question at a time (AskUserQuestion), each with your recommended answer, walking the decision tree branch by branch until it is concrete: what cannot be done today, who is affected, what better looks like, what is out of scope, constraints, the success measure. Answer from the code instead of asking whenever the code can answer.
5. Write every section of intent.md in plain words. Set `Risk: high` when the change touches auth, PII, payments, migrations or infra.
6. `crewforge5 plan check`; fix every listed problem and re-run until `ok`. Show the originator the file and ask them to correct anything misunderstood.

## check
`crewforge5 plan check` and report the verdict.

## accept
Only a human accepts; never accept on the originator's behalf. Ask (AskUserQuestion) the product owner to confirm the intent is correct and in scope. On yes run `crewforge5 plan accept`: it sets `Status: accepted` and commits `plan(<slug>): accept — intent.md` (commit by hand only when the verdict's `checkpoint` says checkpoints are off). Next: `/crewforge5:design new`.

## status
`crewforge5 status` and summarise which artifacts are accepted, present or missing; report `next` verbatim as the command to run.
