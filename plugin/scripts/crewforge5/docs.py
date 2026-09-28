"""Stage documents (spec R-K5, D4): one Archify HTML diagram per stage, delivered from a Claude-authored JSON source.

Mechanics: `docs render|check|open <stage>`, under `<home>/<slug>/docs/`: plan architecture (intent.md), design
dataflow (spec.md), build workflow (plan.md), review sequence (review.md, test-report.json). `check` gates
`plan|design|build accept` and `review review`: refused while the document is missing or stale against its sources
(an artifact's `Status:` line is masked, so accepting never stales its own document). Each is a skipped verdict when
the layer is off (`[docs] enabled = false`, CREWFORGE5_DOCS=off) and when Node or the Archify skill is missing
(skipped, not failed). Nothing here runs inside a hook, and `open` never runs under CI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from . import project as p
from .project import StepSkipped, fail

SKIPPED = {"ok": True, "skipped": "docs disabled"}
INSTALL = ["npx", "-y", "skills", "add", "tt-a1i/archify", "--skill", "archify", "--agent", "claude-code", "--global", "--copy", "--yes"]
INSTALL_CMD = " ".join(INSTALL)
NO_NETWORK = {"ARCHIFY_UPDATE_CHECK_DISABLED": "1"}
SOURCES = {"plan": ["intent.md"], "design": ["spec.md"], "build": ["plan.md"], "review": ["review.md", "test-report.json"]}
DIR_OK = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/-]*$")


def enabled(root: Path) -> bool:
    return p.enabled(root, "docs")


def cfg(root: Path) -> dict:
    """The [docs] table; `dir` is validated here because it becomes a path under the feature directory."""
    conf = p.config(root)["docs"]
    folder = str(conf["dir"])
    if not DIR_OK.match(folder) or ".." in Path(folder).parts or folder.endswith("/"):
        fail(f"[docs] dir {folder!r} must be a relative path made of letters, digits, `.`, `_`, `-` and `/`, without `..`")
    return conf


# --- the installed skill and Node ---


def skill_dir() -> Path:
    return p.claude_dir() / "skills" / "archify"


def installed() -> bool:
    return (skill_dir() / "bin" / "archify.mjs").exists()


def read_quietly(path: Path) -> dict:
    """A JSON object from a file we did not write (the skill's release file, a committed receipt); {} when unreadable."""
    try:
        found = json.loads(path.read_text()) if path.exists() else {}
    except (ValueError, OSError):
        return {}
    return found if isinstance(found, dict) else {}


def version() -> str | None:
    found = read_quietly(skill_dir() / "skill-release.json")
    return str(found["version"]) if isinstance(found, dict) and found.get("version") else None


def node_problem(root: Path) -> str | None:
    """Why Node cannot run Archify here, or None."""
    least = cfg(root)["min_node"]
    major = None
    if shutil.which("node"):
        out = p.run_cmd(root, ["node", "--version"], timeout=10)
        match = re.match(r"v?(\d+)", out.stdout.strip())
        major = int(match.group(1)) if out.returncode == 0 and match else None
    if major is not None and major >= least:
        return None
    return f"node >= {least} required for Archify stage documents (node {'not found' if major is None else f'v{major}'}); install Node, then `{INSTALL_CMD}`"


def tooling(root: Path) -> str | None:
    """Why Archify cannot run here, or None when it can."""
    if why := node_problem(root):
        return why
    return None if installed() else f"Archify skill missing at {skill_dir()}; install it with `{INSTALL_CMD}` (or set [knowledge] auto_install = true and run `crewforge5 knowledge bootstrap`)"


def archify_present(root: Path, conf: dict) -> str | bool:
    """The knowledge bootstrap's `archify` step: skipped when docs are off or Node is unusable."""
    if not enabled(root):
        raise StepSkipped("docs disabled")
    if installed():
        return f"Archify skill {version() or 'unknown'}"
    if why := node_problem(root):
        raise StepSkipped(why)
    return False


def install_archify(root: Path, conf: dict) -> str:
    return p.ran(root, INSTALL, installed)


# --- documents ---


def mechanic(action: str):
    """CLI handler for `docs <action> <stage>`: the skipped verdicts come before any feature lookup."""

    def handler(root: Path, stage: str | None, slug: str | None) -> dict:
        if not enabled(root):
            return dict(SKIPPED)
        if stage not in SOURCES:
            fail(f"unknown stage {stage!r}; one of {', '.join(SOURCES)}", next="crewforge5 docs check plan|design|build|review")
        return ACTIONS[action](root, p.feature(root, slug), stage)

    return handler


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


STATUS_LINE = re.compile(rb"\bStatus:\s*[A-Za-z-]+")


def source_bytes(path: Path) -> bytes:
    """The bytes a document describes: a missing source is empty, and a Markdown artifact's `Status:` field (rewritten
    by accept) is masked, so the pipeline never makes its own document stale."""
    data = path.read_bytes() if path.exists() else b""
    return STATUS_LINE.sub(b"Status: -", data, count=1) if path.suffix == ".md" else data


def digests(root: Path, feature: Path, stage: str) -> tuple[list[dict], str]:
    """Per-source sha256 plus one digest over `<path>\\n<bytes>` for every source, in order."""
    whole = hashlib.sha256()
    entries = []
    for path in (feature / name for name in SOURCES[stage]):
        data = source_bytes(path)
        entries.append({"resource": p.rel(root, path), "digest": sha256(data)})
        whole.update(f"{p.rel(root, path)}\n".encode())
        whole.update(data)
    return entries, whole.hexdigest()


def receipt_of(output: str) -> dict | None:
    """The JSON object `deliver --json` prints (pretty-printed over many lines, after any progress text)."""
    for match in re.finditer(r"^\{", output, re.MULTILINE):
        try:
            found = json.loads(output[match.start() :])
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None


def validation(receipt: dict, quality: str) -> str:
    """`9/9 showcase, 0 errors, 0 warnings`: only integers are copied from the tool's output."""
    v = receipt.get("validation") if isinstance(receipt.get("validation"), dict) else {}

    def count(key: str) -> str:
        value = v.get(key)
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else "?"

    return f"{count('checksPassed')}/{count('checkCount')} {quality}, {count('errors')} errors, {count('warnings')} warnings"


def paths(root: Path, feature: Path, stage: str) -> tuple[Path, Path, Path]:
    folder = feature / cfg(root)["dir"]
    return folder / f"{stage}.json", folder / f"{stage}.html", folder / f"{stage}.receipt.json"


def render(root: Path, feature: Path, stage: str) -> dict:
    conf = cfg(root)
    kind = conf["types"][stage]
    spec, html, receipt_path = paths(root, feature, stage)
    if not spec.exists():
        fail(
            f"stage document source missing; author {p.rel(root, spec)} from {', '.join(SOURCES[stage])} (Archify {kind}), then rerun `crewforge5 docs render {stage}`",
            next=f"author {p.rel(root, spec)} as templates/docs-step.md says",
        )
    if why := tooling(root):
        return {"ok": True, "skipped": why, "next": "continue without the document; its gate is skipped too"}
    argv = ["node", str(skill_dir() / "bin" / "archify.mjs"), "deliver", kind, str(spec), str(html), "--quality", conf["quality"], "--json"]
    out = p.run_cmd(root, argv, NO_NETWORK)
    receipt = receipt_of(out.stdout) if out.returncode == 0 else None
    if receipt is None:
        tail = (out.stderr.strip() or out.stdout.strip())[-400:]
        what = f"exited {out.returncode}" if out.returncode else "printed no receipt (exit 0)"
        fail(f"archify deliver {what}: {tail or 'no output'}", next=f"repair {p.rel(root, spec)} (at most two rounds), then `crewforge5 docs render {stage}`")
    entries, whole = digests(root, feature, stage)
    record = {
        "stage": stage,
        "type": kind,
        "sources": entries,
        "source_digest": whole,
        "specification_sha256": (receipt.get("specification") or {}).get("sha256"),
        "artifact_sha256": (receipt.get("artifact") or {}).get("sha256"),
        "validation": validation(receipt, conf["quality"]),
        "archify_version": version(),
        "delivered_at": p.now_iso(),
    }
    p.write_json(receipt_path, record)
    return {"ok": True, "html": str(html), "receipt": str(receipt_path), "validation": record["validation"], "next": f"crewforge5 docs open {stage}"}


def check(root: Path, feature: Path, stage: str) -> dict:
    """The stage document exists and was delivered from the sources as they are now; skipped when off or untooled."""
    if not enabled(root):
        return dict(SKIPPED)
    if why := tooling(root):
        return {"ok": True, "skipped": why}
    _, html, receipt_path = paths(root, feature, stage)
    entries, whole = digests(root, feature, stage)
    render_cmd = f"crewforge5 docs render {stage} --slug {feature.name}"
    if not html.exists() or not receipt_path.exists():
        fail(f"stage document missing; author {stage}.json in {p.rel(root, html.parent)}, then `{render_cmd}`", html=str(html), source_digest=whole, next=render_cmd)
    receipt = p.read_json(receipt_path, {}) or {}
    if receipt.get("source_digest") != whole:
        before = {e["resource"]: e["digest"] for e in receipt.get("sources", [])}
        changed = [e["resource"] for e in entries if before.get(e["resource"]) != e["digest"]] or [e["resource"] for e in entries]
        fail(f"stage document is stale: {', '.join(changed)} changed since {stage}.html was delivered; rerun `{render_cmd}`", html=str(html), changed=changed, source_digest=whole, next=render_cmd)
    matches = receipt.get("artifact_sha256") == sha256(html.read_bytes())  # evidence for the acceptor, never a block
    return {"ok": True, "html": str(html), "fresh": True, "artifact_matches": matches, "validation": receipt.get("validation"), "source_digest": whole}


def open_(root: Path, feature: Path, stage: str) -> dict:
    """Show the acceptor the delivered document; an opener failure is reported, never a blocked verdict."""
    verdict = check(root, feature, stage)
    if "skipped" in verdict:
        return verdict
    why = "CI set" if os.environ.get("CI") else None if cfg(root)["open"] else "[docs] open = false"
    if why is None:
        out = p.run_cmd(root, ["node", str(skill_dir() / "bin" / "open-artifact.mjs"), verdict["html"]], NO_NETWORK, timeout=10)
        why = None if out.returncode == 0 else (out.stderr.strip() or f"open-artifact.mjs exited {out.returncode}")[-200:]
    return {**verdict, "opened": why is None, **({"note": why} if why else {}), "next": f"quote {verdict['html']} in the acceptance question"}


ACTIONS = {"render": render, "check": check, "open": open_}
VALIDATION_LINE = re.compile(r"^\d+/\d+ [a-z]+, \d+ errors, \d+ warnings$")


def documents(root: Path, feature: Path) -> list[str]:
    """One bullet per delivered stage document with its receipt's validation line; only a well-formed line is copied."""
    folder = feature / str(p.config(root)["docs"]["dir"])
    bullets = []
    for html in sorted(folder.glob("*.html")) if folder.is_dir() else []:
        line = read_quietly(html.with_suffix(".receipt.json")).get("validation")
        bullets.append(f"- {html.stem}: {p.rel(root, html)} ({line if isinstance(line, str) and VALIDATION_LINE.match(line) else 'unrecognised receipt'})")
    return bullets
