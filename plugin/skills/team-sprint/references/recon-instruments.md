# Recon instruments

Three instruments, layered, for every sprint phase that needs codebase evidence:

1. **The repomix pack — the text-evidence instrument.** Every broad sweep —
   "does X already exist", "where does this string occur", "list everything under feature W" —
   goes through one repomix pack of the repo instead of fanning out live Greps or per-file Reads.
   `$SCRIPTS/repomix_refresh.sh` regenerates it; a pack built by hand uses the flags and ignore
   list in the plugin's `templates/repomix-flags.md` (from the retired `use-repo-code` skill).

   **The pack must be freshly regenerated for this sprint — no exceptions.** Force it by deleting
   the pack first, so the refresh always rebuilds:

   ```bash
   rm -f "${REPOMIX_PACK:-.repomix-output.xml}"
   ```

   A claim cited from a stale pack is exactly the kind of drift the reviewers exist to catch —
   don't hand it to them.

   **Search the pack through `rtk` — explicitly, not via the hook.** Do not rely on an RTK
   PreToolUse hook rewriting bare `grep`/`rg` calls; it may not be installed.
   Call `rtk grep` directly for every pack sweep — it truncates lines, caps results, and groups
   hits by file, which is the difference between recon fitting in context and recon drowning it:

   ```bash
   rtk grep '<pattern>' "${REPOMIX_PACK:-.repomix-output.xml}"
   ```

   A hit does not carry its filename: the owning `<file path="...">` tag routinely sits
   hundreds of lines above, so no `-B <n>` window reaches it. Attribute the hit by `Read`ing
   the live file, never by guessing from surrounding pack context.

   Broad sweeps belong in a subagent (the `Explore` agent type): pass it the pack path and the
   instruction *"search the pack with `rtk grep` (bash), not the Grep tool or bare grep."* Bare
   grep against a repomix pack returns full-width XML lines and floods the agent's context.
2. **graphify — the structural instrument** (call sites, reachability, coupling) — below.
3. **Live `Read` — the verification instrument.** Any file/line a finding will *cite* gets
   confirmed against the live tree before it's asserted. Pack and graph are recon; the live
   tree is evidence. When they disagree, the live tree wins.

**Use graphify for the call-site and dependency-mapping recon.** A knowledge graph answers
"what calls X", "what reaches Y", and "are A and B coupled" far better than grep — exactly the two
bullets above. Ensure it's installed for this project and build the graph once, then query it:

```bash
GE=${CREWFORGE5_ROOT}/skills/team-sprint/scripts/graphify_ensure.sh
if [ -x "$GE" ]; then bash "$GE" --ensure; bash "$GE" --graph-status; fi
```

**Route structural questions through the recon router first.** `recon.sh` normalises the
structural intents (`callers`, `callees`, `impact`, `docs`) across codegraph/graphify/repomix
and names the provider and freshness behind every answer, so a provider that cannot parse the
language degrades visibly instead of returning an empty "no callers" that reads as safe:

```bash
RS=${CREWFORGE5_ROOT}/skills/team-sprint/scripts/recon.sh
if [ -x "$RS" ]; then bash "$RS" --probe; bash "$RS" callers "<symbol>"; fi
```

When `recon.sh` is absent (team-sprint not installed), fall back to the graphify CLI below
and to `rtk grep` over the pack — the instruments are unchanged, only the routing is missing.

If `graphify_ensure.sh` is absent (team-sprint not installed) or it reports `STATUS=MISSING`/
`STATUS=STALE`, run the hidden `graphify` skill on the repo root: read
`$PLUGIN/skills/graphify/SKILL.md` and drive it from here. It self-installs graphify and
builds `graphify-out/graph.json`. Then ground recon claims with `graphify query "what calls
<symbol>"`, `graphify path "<A>" "<B>"`, and `graphify explain "<module>"`, citing the
`source_location` each result reports. Keep using grep for exact text/occurrence — graphify
augments it, it doesn't replace it.
