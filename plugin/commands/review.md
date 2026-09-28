---
description: Stage 4 Review — run the checks, review the diff against REVIEW.md, run evals
argument-hint: run | review | evals | status  [--slug <slug>]
allowed-tools: Bash(uv run *), Bash(git *), Read, Write, Edit, Glob, Grep, Agent, Workflow
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control. Knowledge first: run `crewforge5 knowledge bootstrap` (idempotent, check-only unless `[knowledge] auto_install = true`; when not `ok`, say once what is missing and carry on), read the knowledge index its `next` names before raw files, and ask call-graph questions with `graphify query "<question>"` or `graphify affected "<symbol>"` before grep.

Workflows: when `crewforge5 workflows list` reports `enabled: true` and the Workflow tool is available, run the step's workflow as `Workflow({name: "crewforge5:<name>", args: {...}})`; otherwise do the step's inline fallback. Workflows are read-only and advisory: you write the artifact from the result, and the Python gate decides either way. If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook.

Arguments: $ARGUMENTS

## run  (after `/crewforge5:build implement`)
1. `crewforge5 review run` is refused until every Order-of-work step in plan.md has a red→green pair in `tdd.jsonl`; then it runs `[commands] test`, `lint` and `build` from `.crewforge5.toml` and writes `crewforge5/<slug>/test-report.json`.
2. On failure: fix the code, never the test, and rerun. Paste the failing tail in your report.
3. Spawn the `crewforge5:verifier` agent (fresh context) to check the change against plan.md's Proof. Report what it ran and saw.

## review
1. Read `REVIEW.md` at the repo root (copy `${CLAUDE_PLUGIN_ROOT}/templates/REVIEW.md` there if absent) plus intent.md, spec.md, plan.md and `git diff main...HEAD`.
2. `crewforge5 knowledge pack review` (`review review` needs it at HEAD, covering every changed file), then run `crewforge5:review` with `{slug, base: "main", pack}`: Bugs, Security and Compliance passes (the architecture lens folded into Compliance, the boundary lens into Bugs), two skeptics per finding (one refutation downgrades to Nit, two drop it), at most five nits. Write its `markdown` to `crewforge5/<slug>/review.md` as is. Inline fallback: spawn the `crewforge5:reviewer` agent and write its findings there under `## Bugs`, `## Security`, `## Compliance`, each a bullet starting `Important:` or `Nit:` with `path:line`.
3. Address every Important finding with a red→green cycle under the step it belongs to (`/crewforge5:build red|green`), commit, then `crewforge5 review run` again and re-review.
4. Docs: Archify `sequence` from review.md and test-report.json, as `${CLAUDE_PLUGIN_ROOT}/templates/docs-step.md` says: author `docs/review.json`, `crewforge5 docs render review`, `crewforge5 docs open review`.
5. `crewforge5 review review` checks the passing test report, a fresh review document and the review pack are at HEAD, validates review.md, then commits `review(<slug>): review — review.md`. If a mistake was flagged for the second time, add the correction to CLAUDE.md.

## evals
`crewforge5 review evals` runs every `evals/*.json` (`prompt`, `allowed_tools`, `checks`; template `${CLAUDE_PLUGIN_ROOT}/templates/eval.json`) through `claude -p` and gates on `[evals] threshold`. For CI copy `${CLAUDE_PLUGIN_ROOT}/templates/agent-evals.yml` to `.github/workflows/`. Add one eval per production incident.

## status
`crewforge5 status --slug <slug>` and report `next` verbatim.
