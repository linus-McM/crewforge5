---
description: Config hygiene — measure and audit your Claude setup into audit.md; a human accepts the edits
argument-hint: new [<config root>] | check | accept | status  [--slug <slug>]
allowed-tools: Bash(uv run *), Bash(git *), Read, Edit, Write, Glob, Grep, AskUserQuestion, Agent, Workflow
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control. Knowledge first: run `crewforge5 knowledge bootstrap` (idempotent, check-only unless `[knowledge] auto_install = true`; when not `ok`, say once what is missing and carry on), read the knowledge index its `next` names before raw files, and ask call-graph questions with `graphify query "<question>"` or `graphify affected "<symbol>"` before grep.

Workflows: when `crewforge5 workflows list` reports `enabled: true` and the Workflow tool is available, run the step's workflow as `Workflow({name: "crewforge5:<name>", args: {...}})`; otherwise do the step's inline fallback. Workflows are read-only and advisory: you write the artifact from the result, and the Python gate decides either way. If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook.

Arguments: $ARGUMENTS

## new [<config root>]  (read-only: edit nothing but audit.md)
1. `crewforge5 init new [<config root>]` (default `[init] target`, else `.claude/`, else the project) measures the root with token-slim's baseline, the skill and agent validators and the CLAUDE.md, rules, hooks and MCP inventory, then writes `crewforge5/init-<date>/audit.md` with the Baseline filled and `measure.json` beside it.
2. Read `${CLAUDE_PLUGIN_ROOT}/templates/house-rules.md` (the house rules) and `${CLAUDE_PLUGIN_ROOT}/skills/context-hygiene/SKILL.md` (the six principles).
3. Audit: run `crewforge5:config-audit` with `{slug, target}`: five lenses (CLAUDE.md and rules, hooks, MCP, skills, agents), a skeptic per finding. Inline fallback: run context-hygiene passes 2–4 yourself and read each Baseline validator finding against its file, one Agent per lens when it helps.
4. Write Findings (`- Important:` or `- Nit:`, each naming its path), Proposed edits (numbered: the token-slim trims and the skill-rectifier/agent-rectifier fixes, each naming its file and finding) and Retention (lines every trim must keep: never/always directives, exact commands, paths, versions).
5. `crewforge5 init check` until `ok`.

## check
`crewforge5 init check` and report the verdict.

## accept
Only a human accepts. Show the Proposed edits and ask (AskUserQuestion, multiSelect) which to apply; never apply one the human did not pick. Apply exactly those, keeping every Retention line, then run `crewforge5 init accept`: it runs `retention_gate.sh` over every changed instruction file, re-measures, refuses if validator failures rose, records the Result, sets `Status: accepted` and commits `init(<slug>): accept — audit.md`. Then commit the config edits as its `next` says. A breach is fixed by restoring the line, never by weakening the audit.

## status
`crewforge5 init status` and report `next` verbatim.
