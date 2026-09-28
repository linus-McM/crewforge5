# Phase 1 — Plan provenance gate (thin)

**Goal.** Verify the story plan still traces to a `plan.md` a human accepted with `/crewforge5:build accept` **before** the sprint spends a single agent on it. The plan review itself no longer runs here — it ran in `/crewforge5:build new` (`crewforge5:plan-critic`, a skeptic per finding) before the human accepted the plan. This phase only verifies provenance, proves the plan is marker-free, freezes it as `$ART/plan-final.md`, and records it as the plan of record.

## Entry condition

Phase 0 complete. `$ART/state.json.current_phase == 1`. `$plan_path` exists; `$ART` exists.

## Gate

`$SCRIPTS/plan_stories.sh --check` passes over the story plan AND it passes the findings gate (no unfolded `<!-- FINDING ... -->` markers). A failing check → **hard STOP** — do not review the plan yourself, do not warn-and-continue. Surface the script's reason and:

> The story plan no longer traces to an accepted, unchanged plan.md. Accept the plan with `/crewforge5:build accept`, then rebuild the story plan with `/crewforge5:execute --teams`. team-sprint only deploys accepted plans.

## Provenance line contract

`$SCRIPTS/plan_stories.sh` (run by `/crewforge5:execute --teams`) writes one HTML comment on the line directly under the story plan's `#` title:

```
<!-- crewforge5: source=crewforge5/<slug>/plan.md status=accepted sha256=<digest of plan.md> -->
```

- `source` — the feature's `plan.md`; `--check` re-reads it and requires its `Status: accepted` line.
- `sha256` — the digest of `plan.md` when the story plan was built; a changed plan.md fails the check, so the sprint never deploys a plan other than the one accepted.
- A plan.md that also carries the `adversarial-review:` stamp (`[build] require_adversarial_stamp`) keeps it in its own file; the stamp's `rounds` seed `iterations.adversarial` below.

## Steps

1. **Check provenance.**
   ```bash
   bash "$SCRIPTS/plan_stories.sh" --check "$plan_path"
   ```
   `STATUS=FAIL` → STOP with the gate message above.
2. **Findings gate.** `bash "$SCRIPTS/findings_gate.sh" "$plan_path"` must print `STATUS=OK COUNT=0`. `STATUS=FAIL COUNT=<n>` means unresolved `<!-- FINDING ... -->` markers reached the plan — STOP and send it back to `/crewforge5:build`; a marker-laden plan must never reach execution.
3. **Freeze the accepted plan.** `cp "$plan_path" "$ART/plan-final.md"` — Phase 2's entry condition. The plan is frozen from here; Phase 4's AC reviewer checks impl-vs-plan drift directly.
4. **Record the plan of record.**
   ```bash
   bash "$SCRIPTS/state.sh" record-plan "$plan_path" "$ART/plan-final.md"
   ```
   Stores `plan_of_record.{path,sha256}` — the Phase 2 entry gate's `check-plan` proves the accepted plan is the executed plan (obs 18983/18988: a sprint once executed a different plan than the one reviewed).
5. **Persist provenance.** Seed the shared counter (the Phase 2 graph reviewer keeps incrementing it) with the source plan.md's stamp `rounds`, or 0 without a stamp:
   ```bash
   bash "$SCRIPTS/state.sh" update "$plan_path" iterations='{"adversarial":<rounds>,"coverage":0,"review_fix":0}'
   ```

## Exit condition

`$ART/plan-final.md` exists and passes `bash $SCRIPTS/findings_gate.sh "$ART/plan-final.md"` (`STATUS=OK COUNT=0`); plan of record recorded via `state.sh record-plan`; provenance persisted to `state.json.iterations.adversarial`. Advance:
```bash
bash "$SCRIPTS/state.sh" advance-phase "$plan_path" 2
```

## Artifacts produced

- `$ART/plan-final.md` (verbatim copy of the story plan)
- `state.json.plan_of_record` (path + sha256)

## Scripts referenced

- `$SCRIPTS/plan_stories.sh` (`--check`, the provenance gate)
- `$SCRIPTS/findings_gate.sh`
- `$SCRIPTS/state.sh` (`record-plan` at freeze; `advance-phase` at exit)

## References

- `/crewforge5:build` (`commands/build.md` in the plugin) — the plan review (`crewforge5:plan-critic`) and the human acceptance that replaced the retired planner's adversarial-review loop; `templates/adversarial-stamp.md` is the optional stamp.
- `$REF/reviewer-contract.md` — the JSON reviewer return contract, still used by the Phase 2 graph reviewer (mandatory under `scheduling: graph`).

## Extensions

<!-- subskill-hooks:phase-1 -->
RESERVED — `subskill_hooks.phase-1` is NOT active in v1.0. Users who add a `phase-1` block to their config will see an INFO log line `subskill_hooks.phase-1 unsupported in v1.0; block ignored` at Phase 0; the block is NOT persisted into `state.json.subskill_hooks`. See `$REF/subskill-hooks.md` for rationale.
