"""`crewforge5 migrate [<source>] [--slug s]`: move a pre-1.0 run into the feature home once (R-A1, C1).

Two old layouts are carried across:

- a flow run, `.crewforge5/<flow>/<subject>/` (the retired bash flow driver's state), lands in
  `<home>/<subject>/migrated/<flow>/`;
- a plan, `docs/plans/<name>.md` (plus its `<name>-review/` directory when present), lands in
  `<home>/<name>/migrated/`.

Without a source every run found is migrated. The move happens once: the source is gone afterwards and each
feature's `migrated/MIGRATED.json` records what came from where, so a second call is a no-op. A destination that
already exists is never overwritten: the whole call is refused before anything moves.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import artifacts as a
from . import project as p
from .project import fail

OLD_FLOWS = ".crewforge5"
OLD_PLANS = Path("docs/plans")
DIR = "migrated"
RECORD = "MIGRATED.json"


def discover(root: Path) -> list[Path]:
    """Every old run in the project: flow subject directories, then plan files."""
    found: list[Path] = []
    flows = root / OLD_FLOWS
    if flows.is_dir():
        found += sorted(d for flow in flows.iterdir() if flow.is_dir() for d in flow.iterdir() if d.is_dir())
    plans = root / OLD_PLANS
    if plans.is_dir():
        found += sorted(f for f in plans.glob("*.md") if f.is_file())
    return found


def classify(root: Path, source: Path) -> str:
    """`flow` or `plan`; refuses anything else."""
    rel = source.resolve().relative_to(root.resolve()) if source.resolve().is_relative_to(root.resolve()) else None
    if rel is not None and source.is_dir() and len(rel.parts) == 3 and rel.parts[0] == OLD_FLOWS:
        return "flow"
    if rel is not None and source.is_file() and source.suffix == ".md" and rel.parent == OLD_PLANS:
        return "plan"
    return fail(f"{source} is neither a {OLD_FLOWS}/<flow>/<subject>/ run nor a {OLD_PLANS}/<name>.md plan", next="crewforge5 migrate")


def moves(root: Path, source: Path, slug: str | None) -> tuple[str, list[tuple[Path, Path]]]:
    """The feature slug and the (from, to) pairs one source becomes."""
    kind = classify(root, source)
    if kind == "flow":
        slug = slug or a.slugify(source.name) or "run"
        return slug, [(source, p.home(root) / slug / DIR / source.parent.name)]
    slug = slug or a.slugify(source.stem) or "plan"
    target = p.home(root) / slug / DIR
    pairs = [(source, target / source.name)]
    review = source.with_name(f"{source.stem}-review")
    if review.is_dir():
        pairs.append((review, target / review.name))
    return slug, pairs


def recorded(root: Path, source: str) -> str | None:
    """The slug an earlier migrate moved `source` into, if any."""
    home = p.home(root)
    for record in sorted(home.glob(f"*/{DIR}/{RECORD}")) if home.is_dir() else []:
        if any(row.get("source") == source for row in p.read_json(record, [])):
            return record.parent.parent.name
    return None


def tidy(root: Path) -> None:
    """Drop `.crewforge5/<flow>/current` pointers and directories the move left empty."""
    flows = root / OLD_FLOWS
    if not flows.is_dir():
        return
    for flow in [d for d in flows.iterdir() if d.is_dir()]:
        if not any(d.is_dir() for d in flow.iterdir()):
            (flow / "current").unlink(missing_ok=True)
        if not any(flow.iterdir()):
            flow.rmdir()
    if not any(flows.iterdir()):
        flows.rmdir()


def run(root: Path, source: str | None, slug: str | None) -> dict:
    if source:
        path = root / source
        if not path.exists():
            if done := recorded(root, os.path.normpath(source)):
                return {"ok": True, "migrated": [], "already": done, "next": f"crewforge5 status --slug {done}"}
            fail(f"{source} does not exist and was never migrated", next="crewforge5 migrate")
        sources = [path]
    else:
        if slug:
            fail("--slug names the feature for one source; pass the source too", next="crewforge5 migrate <source> --slug <slug>")
        sources = discover(root)
    if not sources:
        return {"ok": True, "migrated": [], "next": "nothing to migrate; crewforge5 status"}
    planned = [(src, *moves(root, src, slug)) for src in sources]
    clashes = [p.rel(root, dst) for _, _, pairs in planned for _, dst in pairs if dst.exists()]
    if clashes:
        fail(f"refusing to overwrite {', '.join(clashes)}; move it aside or pass --slug", clashes=clashes, next="crewforge5 migrate <source> --slug <new slug>")
    migrated = []
    for src, feature_slug, pairs in planned:
        for old, new in pairs:
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
        record = p.home(root) / feature_slug / DIR / RECORD
        rows = p.read_json(record, [])
        rows.append({"source": p.rel(root, src), "to": [p.rel(root, new) for _, new in pairs], "ts": p.now_iso()})
        p.write_json(record, rows)
        migrated.append({"source": p.rel(root, src), "slug": feature_slug, "to": [p.rel(root, new) for _, new in pairs]})
    tidy(root)
    return {
        "ok": True,
        "migrated": migrated,
        "next": f'review and commit {p.rel(root, p.home(root))}/ (each run sits in <slug>/{DIR}/), then carry it into the stages: /crewforge5:plan new "<title>"',
    }
