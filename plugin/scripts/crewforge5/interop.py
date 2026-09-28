"""Interop with cc_sdlc (spec R-X1): `build new --from-sdlc <slug>` takes an accepted `sdlc/<slug>/spec.md` as design input.

CrewForge5 then acts as a crew-powered build stage for cc_sdlc. The cc_sdlc intent.md and spec.md are copied into
`<home>/<slug>/` with a provenance line (`From: sdlc/<slug>/spec.md (accepted)`) and `Status: accepted`, so the
build stage's own gate (an accepted spec.md) holds without a second human accept; nothing is taken from a draft.
The artifact formats are the same (R-X2; `tests/test_interop.py` pins cc_sdlc's section lists).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from . import artifacts as a
from . import project as p
from .project import fail

# cc_sdlc's feature home: SDLC_HOME (as cc_sdlc reads it), else `[interop] sdlc_home` (default "sdlc").
INPUTS = ("intent.md", "spec.md")
FROM_LINE = re.compile(r"^(?:From|Author):[^\n]*$", re.MULTILINE)
AUTHOR = re.compile(r"^(?:From:[^\n]*?\s)?Author:\s*([^.\n]*)\.", re.MULTILINE)


def sdlc_home(root: Path) -> Path:
    name = os.environ.get("SDLC_HOME") or p.config(root)["interop"]["sdlc_home"]
    path = (root / name).resolve()
    if not name or Path(name).is_absolute() or not path.is_relative_to(root.resolve()) or path == root.resolve():
        fail(f"cc_sdlc home {name!r} must be a directory inside the project", next=f"set [interop] sdlc_home in {p.CONFIG_NAME}")
    return root / name


def provenance(source: str) -> str:
    return f"From: {source} (accepted)."


def stamp(md: str, source: str) -> str:
    """Replace the metadata line's provenance with the cc_sdlc source, keeping `Status: accepted` and the risk."""
    risk = a.meta(md, "Risk") or "low"
    author = AUTHOR.search(md)
    by = f" Author: {author.group(1).strip()}." if author else ""
    return FROM_LINE.sub(lambda _m: f"{provenance(source)}{by} Status: accepted. Risk: {risk}.", md, count=1)


def from_sdlc(root: Path, slug: str | None) -> Path:
    """Copy an accepted cc_sdlc intent.md and spec.md into the CrewForge5 feature; the feature directory.

    Refused when the cc_sdlc spec (or its intent) is missing, not accepted, or missing a required section.
    Idempotent: a feature already imported from the same source is reused.
    """
    if not slug or not a.slugify(slug) or a.slugify(slug) != slug:
        fail("--from-sdlc needs a cc_sdlc feature slug", next="/crewforge5:build new --from-sdlc <slug>")
    source_dir = sdlc_home(root) / slug
    feature = p.home(root) / slug
    texts = {}
    for name in reversed(INPUTS):  # the spec first: it is the design input the build stage needs
        src, stage = source_dir / name, "plan" if name == "intent.md" else "design"
        rel = p.rel(root, src)
        if not src.exists():
            fail(f"{rel} missing; cc_sdlc has no accepted {name} for {slug!r}", source=rel, next=f"/sdlc:{stage} status")
        text = src.read_text()
        if a.status(text) != "accepted":
            fail(f"{rel} is not accepted; a human must accept it in cc_sdlc first", source=rel, next=f"/sdlc:{stage} accept")
        if problems := a.section_problems(text, a.REQUIRED[name]):
            fail(f"{rel} does not match the shared format: {'; '.join(problems)}", source=rel, problems=problems, next=f"fix {rel} in cc_sdlc")
        target = feature / name
        if target.exists() and provenance(rel) not in target.read_text():
            fail(f"{p.rel(root, target)} already exists and was not imported from {rel}", slug=slug, next=f"/crewforge5:build status --slug {slug}")
        texts[name] = (text, rel)
    feature.mkdir(parents=True, exist_ok=True)
    for name, (text, rel) in texts.items():  # nothing is written until both inputs pass
        if not (feature / name).exists():
            (feature / name).write_text(stamp(text, rel))
    return feature
