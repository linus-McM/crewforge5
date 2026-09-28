---
description: Stage 2 Design — accepted intent.md to spec.md with concerns; a human accepts it
argument-hint: new | check | accept | status  [--slug <slug>]
allowed-tools: Bash(uv run *), Bash(git *), Read, Edit, Write, Glob, Grep, AskUserQuestion, Workflow
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control. Knowledge first: run `crewforge5 knowledge bootstrap` (idempotent, check-only unless `[knowledge] auto_install = true`; when not `ok`, say once what is missing and carry on), read the knowledge index its `next` names before raw files, and ask call-graph questions with `graphify query "<question>"` or `graphify affected "<symbol>"` before grep.

Workflows: when `crewforge5 workflows list` reports `enabled: true` and the Workflow tool is available, run the step's workflow as `Workflow({name: "crewforge5:<name>", args: {...}})`; otherwise do the step's inline fallback. Workflows are read-only and advisory: you write the artifact from the result, and the Python gate decides either way. The session-start hook sets `CLAUDE_CODE_WORKFLOWS=1` in `.claude/settings.local.json` (`crewforge5 workflows env` does the same on demand).

Arguments: $ARGUMENTS

## new
1. `crewforge5 design new` (refused until intent.md is accepted) writes `crewforge5/<slug>/spec.md`.
2. Read intent.md, CLAUDE.md and the modules the change touches.
3. Design panel: `crewforge5 knowledge pack design` (advisory), then run `crewforge5:design-panel` with `{slug, pack}` (the pack's `path`; omit it when skipped): three designs (minimal, risk-first, longevity), four concern lenses (security, privacy, UX, tech debt) with a skeptic per concern, two judges, one synthesized draft (`requirements`, `trace`, `design`, `concerns`, `open_questions`, `proof`, `rejected`). Inline fallback: sketch the minimal and the risk-first design yourself, pick one and record why the other lost. Keep `rejected` for the plan's Risks.
4. Concerns (the tech-debt audit and triage): audit the files the change touches for debt it would inherit or add, plus security and policy concerns. List each with severity, owner and disposition (fix now, defer, accept risk); say plainly where two policies contradict. Write "none" only when the audit found nothing.
5. Requirements: numbered and testable (R1, R2 ...), each traced to the intent, then a trace table giving every intent goal its disposition: covered by Rn, deferred (with why) or out of scope. No goal may be silently dropped.
6. Design names components, data flow and interfaces; each open question from intent.md is answered or reassigned; Proof names the test files and checks.
7. `crewforge5 design check` until `ok`.

## check
`crewforge5 design check` and report the verdict.

## docs  (before accept)
Archify `dataflow` from spec.md, as `${CLAUDE_PLUGIN_ROOT}/templates/docs-step.md` says: author `docs/design.json`, `crewforge5 docs render design`, then `crewforge5 docs open design`.

## accept
Only a human accepts. Walk the product owner through Concerns first; each must be resolved with its owner before engineering sees the spec. Run `crewforge5 docs open design` (accept is refused while the document is stale), then ask (AskUserQuestion) the product owner to accept; for `Risk: high` also ask for the tech lead's name and record it under Concerns. On yes run `crewforge5 design accept`, which commits `design(<slug>): accept — spec.md`. Next: `/crewforge5:build new`.

## status
`crewforge5 status --slug <slug>` and report `next` verbatim.
