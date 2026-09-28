# Review instructions

## Passes
Run three passes and tag each finding with its pass:
- Bugs: logic errors, broken edge cases, subtle regressions. Boundary lens: across language, repo and deployment boundaries, every input the change assumes has a named producer that can emit it (Assumption Inversion), and the environments, real callers and deployable units that run it match the code (Deployment Reality)
- Security: injection risks, authentication gaps, PII in logs
- Compliance: the change matches crewforge5/<slug>/spec.md, plan.md and our design principles. Architecture lens: SOLID, layering, dependency direction and module boundaries

## Format
Write `crewforge5/<slug>/review.md` with the headings `## Bugs`, `## Security`, `## Compliance`. Each finding is one bullet, `- Important: <problem> (<path>:<line>)` or `- Nit: ...`; a pass with no findings says `- none`. `crewforge5 review review` checks this shape.

## What Important means here
Reserve Important for findings that would break behaviour, leak data or breach a policy. Style and naming are nits.

## Cap the nits
Report at most five nits per review; summarise the rest as a count.

## Do not report
Generated files and anything CI already enforces.
