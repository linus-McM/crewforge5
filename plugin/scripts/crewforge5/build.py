"""Build-stage implementation mechanics (R-T3, R-T4): the accepted-plan gate, plan sync and fix mode.

`build-state.json` in the feature folder is the CLI's own execution state (R-V6): the commit the plan was accepted
at (`accepted_sha`, the base `sync` diffs against) and whether fix mode is on (`fix`, read by the pre-edit hook).
"""

from __future__ import annotations

from pathlib import Path

from . import artifacts as a
from . import crew, stages
from . import project as p
from .project import fail

STATE = "build-state.json"


def load(feature: Path) -> dict:
    data = p.read_json(feature / STATE, {})
    return data if isinstance(data, dict) else {}


def save(feature: Path, **changes) -> dict:
    data = {**load(feature), **changes}
    p.write_json(feature / STATE, data)
    return data


def implementing(root: Path, slug: str | None) -> Path:
    """The feature, provided a human has accepted its plan.md; implementation never starts before that."""
    feature = p.feature(root, slug)
    if not stages.accepted(feature, "plan.md"):
        fail("plan.md is not accepted; implementation starts after a human accepts it", slug=feature.name, next=stages.command("build", "accept", feature.name))
    return feature


def accept(root: Path, slug: str | None) -> dict:
    """`build accept`, then record the commit the plan was accepted at: `sync` diffs against it.

    With `[build] require_crew` on, a valid plan is still refused until its language has a passing crew (R-S5).
    """
    stages.check("build", root, slug)
    crew.require(root)
    verdict = stages.accept("build", root, slug)
    save(Path(verdict["path"]).parent, accepted_sha=p.head(root))
    return verdict


def planned(feature: Path) -> list[str]:
    plan = feature / "plan.md"
    return a.list_items(a.sections(plan.read_text()).get("Files that change", "")) if plan.exists() else []


def owned(root: Path, rel: str) -> bool:
    """The plugin's own output (the feature home, .crewforge5.toml, [checkpoint] paths) is never a plan file."""
    prefixes = [p.rel(root, p.home(root)) + "/", p.CONFIG_NAME, *p.config(root)["checkpoint"]["paths"]]
    return any(rel == pre.rstrip("/") or rel.startswith(pre if pre.endswith("/") else pre + "/") for pre in prefixes)


def changed_since(root: Path, base: str) -> list[str]:
    """Files changed since `base` (committed or not) plus untracked ones; only uncommitted work when there is no base."""
    files = set(p.changed_files(root))
    if base and p.run_git(root, "cat-file", "-e", f"{base}^{{commit}}").returncode == 0:
        files |= set(p.git(root, "diff", "--name-only", base).splitlines())
    return sorted(f for f in files if f)


def sync(root: Path, slug: str | None) -> dict:
    feature = implementing(root, slug)
    base = load(feature).get("accepted_sha", "")
    plan = planned(feature)
    changed = [f for f in changed_since(root, base) if not owned(root, f)]
    if unplanned := [f for f in changed if f not in plan]:
        fail(
            "changed files are missing from plan.md 'Files that change'; add them in the same commit, or revert them",
            slug=feature.name,
            unplanned=unplanned,
            planned=plan,
            base=base,
            next=f"list them in {p.rel(root, feature / 'plan.md')} or revert them, then `crewforge5 build sync`",
        )
    after = f"commit `build({feature.name}): <step>`"
    if tdd_complete(feature):
        after += f"; every step is green: `/simplify` and sync once more, then /crewforge5:review run --slug {feature.name}"
    return {"ok": True, "slug": feature.name, "planned": plan, "changed": changed, "unplanned": [], "base": base, "next": after}


def tdd_complete(feature: Path) -> bool:
    from . import tdd  # tdd imports this module

    return tdd.complete(feature)["complete"]


def fix(root: Path, slug: str | None, state: str | None) -> dict:
    """Bug-fix mode: while on, the pre-edit hook denies edits to test files (`[build] test_globs`)."""
    if state not in ("on", "off"):
        fail("build fix takes on or off", next="crewforge5 build fix on")
    feature = implementing(root, slug)
    save(feature, fix=state == "on")
    after = "test files are read-only: make the committed failing test pass without touching it, then `crewforge5 build fix off`"
    return {"ok": True, "slug": feature.name, "fix": state == "on", "next": after if state == "on" else "crewforge5 build sync"}


def fix_on(root: Path) -> bool:
    """True when any feature has fix mode on: a lock is only safe if no feature's lock can be missed."""
    return any(load(feature).get("fix") for feature in p.features(root))
