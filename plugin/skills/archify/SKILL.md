---
name: archify
model: sonnet
description: Pointer to the Archify skill that renders CrewForge5's stage documents (plan architecture, design dataflow, build workflow, review sequence)
disable-model-invocation: true
---
# Archify stage documents

CrewForge5 does not vendor a diagram tool. Its stage documents are rendered by the third-party
[Archify](https://github.com/tt-a1i/archify) skill, installed into your Claude config, and gated by the
verdict CLI. This skill only points there; it replaces the retired `drawio` skill and execute's phase-8
integration diagram (spec D4).

- **Install** (Node >= 18): `npx -y skills add tt-a1i/archify --skill archify --agent claude-code --global --copy --yes`,
  or set `[knowledge] auto_install = true` in `.crewforge5.toml` and run
  `uv run --no-project "${CLAUDE_PLUGIN_ROOT}/scripts/crewforge5.py" knowledge bootstrap`.
- **Author and render**: follow `${CLAUDE_PLUGIN_ROOT}/templates/docs-step.md` (the `## docs` step of
  `/crewforge5:plan`, `design`, `build` and `review`), then `crewforge5 docs render|check|open <stage>`.
- **Gates**: `plan|design|build accept` and `review review` are refused while the stage document is missing
  or stale; without Node, or with `[docs] enabled = false` / `CREWFORGE5_DOCS=off`, the step is skipped.
- Diagram the code as it is: read the knowledge index and ask `graphify query` / `graphify affected` before
  drawing a box, never from memory.
