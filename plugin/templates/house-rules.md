# House rules for editing a Claude config

From the retired `claude-config` skill (spec phase 8). `/crewforge5:init new` reads this as the bar every
proposed edit is judged against, for any config root under edit: a user's `$CLAUDE_CONFIG_DIR`, a
project's `.claude/`, or a plugin's own tree. These are the non-obvious constraints; everything else is
inferable from the tree.

## The repo

Read the target root's `.gitignore` before staging anything: it is the source of truth for what syncs,
and config repos commonly use a **whitelist** (`/*` ignores everything at root, `!/name` re-includes
entries). In a whitelist repo, tracking a NEW root file needs its `!/<name>` rule first, otherwise `/*`
hides it and `git add` silently skips it (`git add -f` stages it once but doesn't persist intent).

If the root carries a `settings.json` that syncs across machines, keep it portable: no machine-specific
paths, and name the install step for any tool a hook needs.

## Frontmatter

- `model:` by judgment tier: haiku = mechanical, sonnet = structured work, opus = judgment/taste.
- `context: fork` + `agent:` only for autonomous report-producing skills. Anything with an
  AskUserQuestion intake gate or an interactive loop must stay inline, since a forked subagent has no
  user to ask.
- `disable-model-invocation: true` when a skill is an expensive deliberate ritual: it drops from the
  always-loaded catalog and `/<name>` still works. Check first that nothing invokes it through the Skill
  tool, which cannot reach a hidden skill.
- `tools:` quotes the wildcard as `"*"`. Bare `*` is a YAML alias and does not parse.

## Size

`description:` loads in every session; the body does not. Keep descriptions under ~200 chars, keep the
double-quoted trigger phrases (they drive matching), and put detail in the body or `references/`.

Project-specific agents belong in that project's `.claude/agents/`, not in a user-level `agents/`: a
user-level agent costs its description in every session in every repo.

The self-improve skill's `scripts/ceiling.sh check` holds every skill and agent to a recorded byte
budget; run it after editing one. `ceiling.sh record <target>` moves a budget deliberately, in a
reviewable diff.

## Gates

For this plugin's own tree, run its release gates after any edit (`scripts/budget_check.sh`,
`scripts/name_check.sh`, `scripts/validate_all.sh` under the plugin root); all three must pass.

Agent definitions must not restate CLAUDE.md or a rules file: duplicates drift and contradict; point at
the one home instead.
