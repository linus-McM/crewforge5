"""Review stage (R-T2, R-A3): `review run` runs the feedback loop, `review review` validates review.md.

`run` is refused until every Order-of-work step has a red->green pair in tdd.jsonl (`tdd.require`), then runs
`[commands] test|lint|build` and writes `test-report.json`. `review` checks `review.md` against REVIEW.md's three
passes (`## Bugs`, `## Security`, `## Compliance`; each finding a bullet `Important:` or `Nit:` naming `path:line`,
at most five nits) and is a stage boundary: `cli.main` checkpoints it as `review(<slug>): review — review.md`.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import artifacts as a
from . import build, docs, packs, stages, tdd
from . import project as p
from .project import fail

REPORT = "test-report.json"
REVIEW = "review.md"
CHECKS = ("test", "lint", "build")
NITS = 5
BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
FINDING = re.compile(r"^(?:\*\*)?(Important|Nit)(?:\*\*)?:\s*(.*)$")
LOCATION = re.compile(r"(?:[\w.@+-]+/)*[\w.@+-]*[A-Za-z_][\w.@+-]*:\d+")  # src/feat.py:3, Makefile:12
REVIEWED = "merge the branch: the feature is reviewed"


def command(action: str, slug: str) -> str:
    return stages.command("review", action, slug)


def run(root: Path, slug: str | None) -> dict:
    feature = build.implementing(root, slug)
    evidence = tdd.require(feature)
    commands = p.config(root)["commands"]
    if not commands["test"].strip():
        fail(f"no test command: set [commands] test in {p.CONFIG_NAME}", slug=feature.name, next=f'add `test = "<command>"` under [commands] in {p.CONFIG_NAME}')
    results = [{"name": name, **tdd.run_tests(root, cmd)} for name in CHECKS if (cmd := str(commands.get(name, "")).strip())]
    failed = [r["name"] for r in results if r["exit"] != 0]
    path = feature / REPORT
    p.write_json(path, {"passed": not failed, "results": results, "steps": evidence["steps"], "sha": p.head(root), "ts": p.now_iso()})
    if failed:
        fail("checks failed: fix the code, not the tests", slug=feature.name, failed=failed, results=results, path=str(path), next=f"fix the code, then {command('run', feature.name)}")
    after = f"spawn crewforge5:verifier, write {p.rel(root, feature / REVIEW)} against REVIEW.md, then {command('review', feature.name)}"
    return {"ok": True, "slug": feature.name, "path": str(path), "failed": [], "results": results, "next": after}


def findings(text: str) -> tuple[list[str], dict]:
    """Problems with a review.md body, and its Important/Nit counts."""
    problems = a.section_problems(text, a.REQUIRED[REVIEW])
    found = a.sections(text)
    counts = {"important": 0, "nits": 0}
    for heading in a.REQUIRED[REVIEW]:
        for line in found.get(heading, "").splitlines():
            if not (bullet := BULLET.match(line)):
                continue
            item = bullet.group(1).strip()
            if item.lower().rstrip(".") == "none":
                continue
            if not (tag := FINDING.match(item)):
                problems.append(f"{heading}: a finding must start `Important:` or `Nit:` ({item[:60]})")
                continue
            if not LOCATION.search(tag.group(2)):
                problems.append(f"{heading}: a finding must name its path:line ({item[:60]})")
            counts["important" if tag.group(1) == "Important" else "nits"] += 1
    if counts["nits"] > NITS:
        problems.append(f"{counts['nits']} nits listed; at most {NITS}, summarise the rest as a count")
    return problems, counts


def review(root: Path, slug: str | None) -> dict:
    """The stage's exit: a passing test report at HEAD, then a valid review.md."""
    feature = build.implementing(root, slug)
    report = p.read_json(feature / REPORT, {})
    if not (isinstance(report, dict) and report.get("passed")):
        fail(f"no passing {REPORT}; run the checks first", slug=feature.name, next=command("run", feature.name))
    if report.get("sha") != p.head(root):
        fail(f"{REPORT} is stale: HEAD moved since `review run`", slug=feature.name, next=command("run", feature.name))
    path = feature / REVIEW
    if not path.exists():
        fail(f"{REVIEW} missing; run the review passes from REVIEW.md and write the findings", slug=feature.name, next=f"write {p.rel(root, path)}, then {command('review', feature.name)}")
    problems, counts = findings(path.read_text())
    if problems:
        fail("; ".join(problems), slug=feature.name, path=str(path), problems=problems, next=f"fix {REVIEW}, then {command('review', feature.name)}")
    document = docs.check(root, feature, "review")  # R-K5: the review sequence document is fresh
    pack = packs.require(root, feature, "review")  # R-K3: a review pack at HEAD covering every changed text file
    after = REVIEWED
    if counts["important"]:
        after = f"address each Important finding with a `/crewforge5:build red|green` cycle, then {command('run', feature.name)} and re-review"
    return {"ok": True, "slug": feature.name, "path": str(path), **counts, "document": document, "pack": pack, "next": after}


def next_for(feature: Path) -> str:
    """After an accepted plan.md: implement until TDD is complete, then run, then review (for `status`)."""
    if not tdd.complete(feature)["complete"]:
        return stages.AFTER_BUILD
    report = p.read_json(feature / REPORT, {})
    if not (isinstance(report, dict) and report.get("passed")):
        return command("run", feature.name)
    path = feature / REVIEW
    if not path.exists() or findings(path.read_text())[0]:
        return command("review", feature.name)
    return REVIEWED
