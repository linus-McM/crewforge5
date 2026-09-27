# recon.sh output grammar (contract fixture)

The single source of truth for recon.sh's status set. `recon.bats` and
`recon_guard.bats` read their STATUS= and REASON= lists from this file rather
than restating them, so a new status cannot be added in one place and go
untested in the other. Carried over from the recon-harness-1 sprint plan, which
no longer ships with the plugin.

## Output grammar

One shape regardless of provider, so callers parse once. **This block is the single source of
truth for the status set** — RH1's contract-coverage loop reads its status list from here rather
than restating it, so a new status cannot be added in one place and go untested in the other.

```
PROVIDER=<name> INTENT=<intent> FRESHNESS=<live|fresh|stale:<n>m|none> QUERY=<arg>
<path>:<line>\t<symbol>\t<relation>
...
STATUS=<OK|EMPTY|UNAVAILABLE|SKIP|DEGRADED|NO_INTENT_MATCH|DELEGATE> [COUNT=<n>] [REASON=<r>] [FILES=<n>] [PROVIDER=<name>] [TOOL=<name>] [ARGS=<json>]
```

- `STATUS=` is mandatory, is always the last line, and takes exactly one of those seven values — there is no eighth, and a value not on this list is a bug, not an extension.
- The leading `PROVIDER= INTENT= FRESHNESS= QUERY=` header line is emitted on the two answer statuses (`OK`, `EMPTY`) only; every other status is a single `STATUS=` line with no header and no body.
- `COUNT=<n>` is mandatory on `OK` and `EMPTY` and omitted on the five non-answer statuses, where there is no result set to count.
- `REASON=<r>` is mandatory on `SKIP`, `UNAVAILABLE` and `DEGRADED`, and omitted elsewhere. Closed vocabulary: `disabled`, `small-repo`, `not-a-repo`, `not-installed`, `no-index`, `language-unsupported`, `provider-error`.
- `FILES=<n>` appears only on `STATUS=SKIP REASON=small-repo`, reporting the file count RH3's guard actually measured, and on `STATUS=SKIP REASON=not-a-repo FILES=0`, where there is no repo to count.
- `PROVIDER=` appears in the header line on `OK`/`EMPTY`, and again on the `STATUS=DELEGATE` line to name the provider being delegated to; `ARGS=` appears on `STATUS=DELEGATE` only, as does `INTENT=`, which the delegating agent needs to pick the tool. `TOOL=` appears there only when the probe read that name off a live MCP roster — bash cannot enumerate an MCP roster, so a hardcoded tool name is forbidden and a nameless `DELEGATE` line is well-formed.
- `STATUS=DELEGATE` is terminal only for a caller that can make MCP calls. Under `--no-delegate` / `RECON_NO_MCP=1` an MCP-only link is skipped exactly as an absent provider is, and the chain advances.
- Result lines are capped at `RECON_MAX_LINES` (default 50); a truncated body ends with one `TRUNCATED=<emitted>/<total>` line, the only body line exempt from the `<path>:<line>` shape, and `COUNT=` still reports the pre-truncation total.

`FRESHNESS=` is mandatory on `OK` and `EMPTY` and takes one of `live|fresh|stale:<n>m|none`.
`none` is the no-index-consulted value, deliberately matching the condition `graphify_ensure.sh`
reports as `STATUS=MISSING` (`graphify_ensure.sh:34`). It is **omitted entirely**, not set to
`none`, on `SKIP`/`DEGRADED`/`UNAVAILABLE`/`NO_INTENT_MATCH`/`DELEGATE`, consistent with the
optional-key rule above — those statuses emit no header line at all; RH4's call log, which is
fixed-arity JSON rather than a line grammar, records the field as `null` in exactly those cases.
The three providers have different staleness models — CodeGraph auto-syncs (`union.md:128-133`,
~2s debounce via FSEvents), graphify and repomix are manual and age-gated — and a caller cannot

## Contract-coverage gate

- Every intent in the 10-intent table is named in at least one `bats` test.
- Every `STATUS=` value in the Output grammar block — that block, not a per-script restatement of it — has a test asserting it is emitted, and every value a script's header documents appears in that block.
- Every `REASON=` value in the output grammar's closed vocabulary — all seven of `disabled small-repo not-a-repo not-installed no-index language-unsupported provider-error`, the list read from that block rather than trimmed here — has a test asserting it is emitted with its status, and no value may sit outside every story's loop.
