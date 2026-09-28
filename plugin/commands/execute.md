---
description: Shortcut — build implement then review on an accepted plan.md; --teams runs the Teams sprint path
argument-hint: "[--slug <slug>] [--teams]"
allowed-tools: Bash(uv run *), Bash(git *), Bash(bash *), Read, Edit, Write, Glob, Grep, AskUserQuestion, Agent, Skill, Workflow
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control. Knowledge first: run `crewforge5 knowledge bootstrap` (idempotent, check-only unless `[knowledge] auto_install = true`; when not `ok`, say once what is missing and carry on), read the knowledge index its `next` names before raw files, and ask call-graph questions with `graphify query "<question>"` or `graphify affected "<symbol>"` before grep.

If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook.

Arguments: $ARGUMENTS

This is the shortcut (spec R-S7); `/crewforge5:build` and `/crewforge5:review` are the primary surface. It adds no gate of its own: every gate is the verdict of a command it runs.

## run  (the default)
1. `crewforge5 status --slug <slug>` (no slug: the latest feature). Unless `plan.md` is `accepted`, stop and follow its `next`; never accept on anyone's behalf.
2. Run, in order and each exactly as its command file says: `/crewforge5:build implement --slug <slug>` (`${CLAUDE_PLUGIN_ROOT}/commands/build.md`: red then green per step, the `crewforge5:story-executor` waves, sync, `/simplify`), then `/crewforge5:review run --slug <slug>` and `/crewforge5:review review --slug <slug>` (`${CLAUDE_PLUGIN_ROOT}/commands/review.md`: the checks and `crewforge5:verifier`, then the `crewforge5:review` workflow and its checkpoint). Stop at the first verdict that is not `ok`.
3. Distil: `bash "${CLAUDE_PLUGIN_ROOT}/skills/self-improve/scripts/ledger.sh" count`; when it is above zero, read `${CLAUDE_PLUGIN_ROOT}/skills/self-improve/SKILL.md` and follow its Run section (every edit net-neutral or smaller), then `bash "${CLAUDE_PLUGIN_ROOT}/skills/self-improve/scripts/ceiling.sh" check` must pass. An empty ledger is a clean run.
4. Print the underlying commands you ran, one per line.

## --teams  (graph-mode Teams path; kept until measured, spec D3)
1. `crewforge5 status --slug <slug>`: unless `plan.md` is `accepted`, stop and follow its `next`.
2. `bash "${CLAUDE_PLUGIN_ROOT}/skills/team-sprint/scripts/plan_stories.sh" <home>/<slug>/plan.md` (home `crewforge5/` unless `[project] home` says otherwise) writes `sprint-<slug>.md` beside it: one story per Order-of-work step, the human acceptance as its provenance line. On `STATUS=FAIL` quote the reason and stop.
3. Read `${CLAUDE_PLUGIN_ROOT}/skills/team-sprint/SKILL.md` (hidden: the Skill tool cannot reach it) and run its phases 0–7 on that story plan with `scheduling: graph`. Its own state lives in `.team-sprint/sprints/`; its Phase 7 fleet reviews the sprint diff and merges.
4. Distil as in run step 3, then print the commands you ran. The Teams path writes no `tdd.jsonl`, so `review run` refuses a feature it built; the two paths stay side by side until one real sprint has been measured both ways (C4).
