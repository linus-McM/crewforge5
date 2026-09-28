---
description: Crew factory — survey the stack, forge and validate a per-language agent crew
argument-hint: survey | forge <lang> | validate [<lang>] | status [<lang>]
allowed-tools: Bash(uv run *), Bash(git *), Read, Glob, Grep, AskUserQuestion, Agent
---
Run every `crewforge5` call as `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" ...` from the project root. Each call prints one JSON verdict: act on `ok`, quote `reason` verbatim when false, and follow `next`. Never edit the verdict logic; the gate is the control. Knowledge first: run `crewforge5 knowledge bootstrap` (idempotent, check-only unless `[knowledge] auto_install = true`; when not `ok`, say once what is missing and carry on), read the knowledge index its `next` names before raw files, and ask call-graph questions with `graphify query "<question>"` or `graphify affected "<symbol>"` before grep.

If a hook denies a command, quote the denial; never rewrite, encode, split or relocate a command to get past a hook.

Arguments: $ARGUMENTS

## survey
1. `crewforge5 crew survey` detects the language (`[project] language`, else `detect_language.sh`). On AMBIGUOUS or UNKNOWN ask the user (AskUserQuestion) and record the answer as `[project] language` in `.crewforge5.toml`.
2. Without a profile, spawn the `crewforge5:stack-surveyor` agent with the language; it writes `.claude/crews/<lang>.profile.md`, every command verified. Report its `unverified_count`.

## forge <lang>
1. Spawn the `crewforge5:crew-factory` agent with the language. It reads the profile (running the surveyor itself when missing), generates and validates each role agent to grade A, and writes `.claude/crews/<lang>.json` and `.claude/rules/<lang>.md`. Wait for it; if it escalates an agent it cannot bring to grade A, report that and stop.
2. `crewforge5 crew validate <lang>` must be `ok`. On `worktree_agents` other than `ok`, tell the user the generated agents are invisible to worktree sprints until they are committed (`git add .claude/agents .claude/crews .claude/rules`); do not commit for them.

## validate [<lang>]
`crewforge5 crew validate [<lang>]` runs `crew_check.sh check`, re-grades every generated agent with the agent validator and checks the manifest's `validation` grades. On `ok` it copies the manifest's `test`/`lint`/`build` commands into `.crewforge5.toml`'s empty `[commands]` keys (`commands_adopted`); tell the user to commit that. On a refusal, follow `next` (`/crewforge5:crew forge <lang>`).

## status [<lang>]
`crewforge5 crew status [<lang>]` lists each crew, its roles and grades; report `next` verbatim. With `[build] require_crew = true`, `build accept` refuses until the plan's language has a passing crew.
