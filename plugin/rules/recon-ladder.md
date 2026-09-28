---
description: Codebase recon escalation ladder used by team-sprint, the stage commands and their review and audit agents.
---

# Codebase recon instruments

Escalation ladder — the convention team-sprint, the stage commands and their review and
audit agents all follow.
**Rule: never escalate a tier you can answer at a lower one.**

| Tier | Instrument | Use when |
| --- | --- | --- |
| 0 | Live `Read` | target file known, ≤3 files; anything you cite is confirmed here |
| 1 | `recon.sh text` | text/occurrence, location unknown |
| 2 | `recon.sh <structural intent>` | what calls X, reachability, coupling |
| 3 | full index rebuild | index missing or stale |

Tier 1 greps the pack with **explicit `rtk grep`**, not bare grep —
the hook is best-effort; see the rtk notes in the CrewForge5 README. To force a fresh
pack when grounding a plan or review, delete the pack first (`rm -f .repomix-output.xml`), then
rebuild it (`${CREWFORGE5_ROOT}/templates/repomix-flags.md` has the flags). Tiers 1–2 route through
`${CREWFORGE5_ROOT}/skills/team-sprint/scripts/recon.sh`, which names its provider and freshness, so a
provider that cannot parse the language degrades visibly instead of answering an empty "no
callers"; its header documents the rest. Tier 2 otherwise uses `graphify query` / `path` /
`explain`; on `/graphify`, invoke the Skill tool before anything else.

<!-- SOUL.md = how to be (tone, opinions, boundaries). This file = how to work.
     Both are required; both are inlined below, so neither needs a Read. -->
