# Concern dimensions

From the retired `tech-debt-audit` skill (spec phase 8). `/crewforge5:design new` audits the files the
change touches along these dimensions and writes each finding under spec.md's **Concerns** with severity,
owner and disposition (fix now, defer, accept risk). Cite `path/to/file.ext:LINE` for every finding and
confirm each against the live file: the pack and the graph are recon, the live tree is evidence.

1. **Architectural decay**: circular deps, layering violations, god files (>500 LOC) and god functions,
   logic duplicated across 3+ sites, abstractions nobody uses, dead code. Instrument: `graphify query`
   for coupling and cycles, zero-caller queries for dead code; else grep for the same signals.
2. **Consistency rot**: several ways of doing one thing (HTTP clients, error handling, logging, config
   loading, validation, dates); naming drift; folder structure that no longer matches the code.
3. **Type and contract debt**: `any` / `as any` / `# type: ignore` / loose dicts; untyped API
   boundaries; missing schema validation at trust boundaries.
4. **Test debt**: coverage gaps on critical paths (run the project's coverage command when it has one);
   tests asserting implementation rather than behaviour; skipped or flaky tests; high-churn files with no
   tests.
5. **Dependency and config debt**: known CVEs (the stack's audit tool), unused or duplicate deps, env var
   sprawl (referenced but undocumented, defaults inconsistent across environments).
6. **Performance and resource hygiene**: N+1 queries, sync work in async paths, blocking I/O on hot
   paths, uncleaned listeners or handles, needless serialization.
7. **Error handling and observability**: swallowed exceptions, blanket catches, errors logged but not
   handled, inconsistent error shapes, missing structured logs on critical paths.
8. **Security hygiene**: hardcoded secrets, string-concatenated SQL, missing input validation at trust
   boundaries, permissive auth or CORS, weak crypto. Live-read every hit before citing it.
9. **Documentation drift**: README claims that no longer hold, comments contradicting adjacent code,
   public APIs without docstrings.

Say plainly where two policies contradict. Write "none" only when the audit found nothing.
