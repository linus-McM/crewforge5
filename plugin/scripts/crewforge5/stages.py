"""The ordered stage table and the new/check/accept lifecycle shared by intent.md, spec.md and plan.md."""

from __future__ import annotations

from pathlib import Path

from . import artifacts as a
from . import docs
from . import project as p
from .project import fail

# stage -> the artifact it writes. The order is the pipeline: each accepted artifact gates the next stage.
ARTIFACTS = {"plan": "intent.md", "design": "spec.md", "build": "plan.md"}
ORDER = list(ARTIFACTS)
# An accepted plan.md goes to the execute alias (R-S7): `/crewforge5:build implement`, then `/crewforge5:review run|review`.
AFTER_BUILD = "/crewforge5:execute"


def command(stage: str, action: str, slug: str | None = None) -> str:
    return f"/crewforge5:{stage} {action}" + (f" --slug {slug}" if slug else "")


def prerequisite(stage: str) -> str | None:
    i = ORDER.index(stage)
    return ARTIFACTS[ORDER[i - 1]] if i else None


def next_stage(stage: str, slug: str) -> str:
    i = ORDER.index(stage) + 1
    return command(ORDER[i], "new", slug) if i < len(ORDER) else AFTER_BUILD


def accepted(feature: Path, artifact: str) -> bool:
    path = feature / artifact
    return path.exists() and a.status(path.read_text()) == "accepted"


def gated(root: Path, slug: str | None, stage: str) -> Path:
    """The feature directory, provided the stage's prerequisite artifact has been accepted by a human."""
    feature = p.feature(root, slug)
    if (artifact := prerequisite(stage)) is None:
        return feature
    before = ORDER[ORDER.index(stage) - 1]
    if not (feature / artifact).exists():
        fail(f"{artifact} missing; run the previous stage first", slug=feature.name, next=command(before, "new", feature.name))
    if not accepted(feature, artifact):
        fail(f"{artifact} is not accepted; a human must accept it before this stage", slug=feature.name, next=command(before, "accept", feature.name))
    return feature


def create_feature(root: Path, title: str) -> Path:
    if not title.strip() or not a.slugify(title):
        fail("plan new needs a title", next=command("plan", 'new "<title>"'))
    feature = p.home(root) / a.slugify(title)
    if (feature / "intent.md").exists():
        fail(f"{p.rel(root, feature / 'intent.md')} already exists", slug=feature.name, next=command("plan", "check", feature.name))
    feature.mkdir(parents=True, exist_ok=True)
    return feature


def new(stage: str, root: Path, title: str | None, slug: str | None) -> dict:
    artifact = ARTIFACTS[stage]
    if stage == "plan":
        feature = create_feature(root, title or "")
        fields = {"title": (title or "").strip(), "author": p.author(root), "risk": "low"}
    else:
        feature = gated(root, slug, stage)
        if (feature / artifact).exists():
            fail(f"{artifact} already exists", slug=feature.name, next=command(stage, "check", feature.name))
        intent = (feature / "intent.md").read_text()
        fields = {"title": a.title(intent), "risk": a.meta(intent, "Risk") or "low"}
    path = feature / artifact
    path.write_text(a.render(p.TEMPLATES / artifact, date=p.today(), **fields))
    created = p.ensure_config(root)  # the first `new` writes .crewforge5.toml (R-C1)
    return {
        "ok": True,
        "slug": feature.name,
        "path": str(path),
        "config_created": created,
        "next": f"fill every section of {artifact}, then {command(stage, 'check', feature.name)}",
    }


def check(stage: str, root: Path, slug: str | None) -> dict:
    artifact = ARTIFACTS[stage]
    feature = gated(root, slug, stage)
    path = feature / artifact
    if not path.exists():
        fail(f"{artifact} missing", slug=feature.name, next=command(stage, "new", feature.name))
    text = path.read_text()
    problems = a.validate(text, a.REQUIRED[artifact])
    if stage == "build":
        problems += a.plan_problems(text)
    if stage == "build" and p.config(root)["build"]["require_adversarial_stamp"] and not a.stamped(text):
        problems.append("missing adversarial-review stamp (status=clean or status=user-override); [build] require_adversarial_stamp is on")
    if problems:
        fail("; ".join(problems), slug=feature.name, path=str(path), problems=problems, next=f"fix {artifact}, then {command(stage, 'check', feature.name)}")
    risk = a.meta(text, "Risk")
    return {"ok": True, "slug": feature.name, "path": str(path), "risk": risk, "problems": [], "next": command(stage, "accept", feature.name)}


def accept(stage: str, root: Path, slug: str | None) -> dict:
    """Only a human accepts: the command asks (AskUserQuestion) before it calls this."""
    verdict = check(stage, root, slug)
    path = Path(verdict["path"])
    document = docs.check(root, path.parent, stage)  # R-K5: refused while the stage document is missing or stale
    path.write_text(a.set_meta(path.read_text(), "Status", "accepted"))
    return {**verdict, "status": "accepted", "document": document, "next": next_stage(stage, verdict["slug"])}


def state(feature: Path) -> dict[str, str]:
    """Each artifact's state: accepted, draft or missing."""
    out = {}
    for name in ARTIFACTS.values():
        path = feature / name
        out[name] = (a.status(path.read_text()) or "draft") if path.exists() else "missing"
    return out


def next_for(feature: Path, states: dict[str, str]) -> str:
    """The one command to run next for a feature, derived from its artifacts on disk."""
    for stage, artifact in ARTIFACTS.items():
        if states[artifact] == "missing":
            return command(stage, "new", feature.name)
        if states[artifact] != "accepted":
            return command(stage, "check", feature.name)
    from . import review  # review imports build, which imports this module

    return review.next_for(feature)


def status(root: Path, slug: str | None) -> dict:
    """With a slug: that feature's artifacts. Without: every feature, and the next command for the most recent (R-S6)."""
    if slug:
        feature = p.feature(root, slug)
        states = state(feature)
        return {"ok": True, "slug": feature.name, "artifacts": states, "next": next_for(feature, states)}
    listed = []
    for feature in p.features(root):
        states = state(feature)
        listed.append({"slug": feature.name, "artifacts": states, "next": next_for(feature, states)})
    if not listed:
        return {"ok": True, "features": [], "next": command("plan", 'new "<title>"')}
    latest = p.feature(root, None).name
    return {"ok": True, "features": listed, "latest": latest, "next": next(f["next"] for f in listed if f["slug"] == latest)}
