# Interview: diverge, then grill

From the retired `adhd` and `grill-me` skills (spec phase 8). `/crewforge5:plan new` uses both before it
writes intent.md.

## Diverge

Before asking anything, frame the goal at least three ways: the literal ask, the smallest version that
helps, and the version that removes the underlying problem. Then run up to five vantage frames from the
catalogue below over it (for code-shaped goals four tagged `code` or `design` plus one `wild`; for product
or strategy goals a mix). Note what each framing leaves out; keep the ones that change the question.

| Frame | Vantage prompt | Tags |
|---|---|---|
| **hardware engineer** | You think in latency, memory layout, and physical constraints. Re-ask this as a hardware/firmware problem. What does the bus topology, cache, timing budget tell you? | code, wild |
| **regulator** | You audit systems for compliance and failure modes. What must be provable, traceable, or refusable here? | design, general |
| **10-year-old** | You are a curious 10 year old who has never seen software. Describe naive but unencumbered approaches. Ignore convention. | general, wild |
| **competitor trying to break it** | You are a hostile competitor or attacker. Generate approaches that exploit, fail, or sabotage the obvious solution. Then invert into ideas. | code, design |
| **biology** | Transplant a mechanism from biology (immune systems, neural plasticity, cell signaling, evolution, gut flora). Force-fit it onto this engineering problem. | code, wild |
| **logistics** | Steal mechanisms from logistics: queues, batching, just-in-time, hub-and-spoke, returns, last-mile. Apply them literally. | code, design |
| **game design** | Approach this as a game designer. What are the loops, rewards, friction, save-states, speedrun tricks? Treat the user as a player. | design, general |
| **markets** | Treat the problem as a market. Buyers, sellers, market-makers. What does an auction, a futures contract, a clearing house look like here? | design, wild |
| **inversion** | Ask the OPPOSITE question. If goal is X, brainstorm how to guarantee NOT X. Then negate each answer back. | code, design, general |
| **extreme: $0 budget, 1 hour** | No money, no team, one hour. What is the crudest version that still does the load-bearing thing? | code, general |
| **extreme: infinite budget, 10 years** | Infinite compute, infinite engineers, a decade. What is the maximalist version? | design, wild |
| **remove the load-bearing assumption** | Name the thing everyone treats as fixed (framework, database, request-response model, network). Imagine it is gone. What is possible? | code, design, wild |
| **speedrunner** | You are a speedrunner. Find glitches, skips, out-of-bounds tricks, frame-perfect shortcuts. What is the abusive-but-legal path? | code, wild |
| **ant colony** | No central planner. Many dumb agents, local rules, pheromone trails. How does the problem solve itself emergently? | code, wild |
| **3am on-call** | You are the on-call engineer woken at 3am when this breaks. What design would let you not get paged? | code, design |


## Grill

Interview the originator until you reach a shared understanding. Walk down each branch of the decision
tree, resolving dependencies between decisions one by one. Ask one question at a time (AskUserQuestion),
each with your recommended answer, and wait for the answer before the next; several at once is
bewildering. If a *fact* can be found in the repo (the knowledge index, `graphify query`, the code),
look it up instead of asking. The *decisions* belong to the originator: put each one to them. Do not act
until they confirm the understanding is shared.

Cover at least: what cannot be done today, who is affected, what better looks like, what is out of scope,
the constraints, and the success measure.
