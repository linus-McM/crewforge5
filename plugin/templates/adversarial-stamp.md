# Adversarial-review stamp

From the retired `adversarial-review` and `team-sprint-planner` skills (spec R-S3, phase 8). The stamp is a
precondition `build check` enforces when `[build] require_adversarial_stamp = true`; it never replaces the
human `build accept`.

**When.** Only after a critique round comes back dry: run `crewforge5:plan-critic` (or its inline lenses),
apply or explicitly reject every confirmed finding, then run it once more over the final text. Stamp only
after that verifying round reports no new confirmed Important finding; never stamp a text you just edited.
Nits are applied in the same pass and never gate. Hard cap: two close-out rounds. Still not dry after
that, the human decides (fix by hand, extend, or accept the residuals, which is `status=user-override`).
The critique never overrides itself.

**What.** One line directly under plan.md's `#` title, in exactly this shape (the gate greps it):

```
<!-- adversarial-review: status=<clean|user-override> rounds=<N> date=<YYYY-MM-DD> reviewer=crewforge5:plan-critic -->
```

- `status` is `clean` (the last round was dry) or `user-override` (a human waived named residuals;
  list them under Risks).
- `rounds` counts the critique rounds run.
- One stamp only: a plan carrying two reviewer stamps has no provenance.
