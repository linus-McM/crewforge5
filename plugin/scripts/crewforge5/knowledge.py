"""Knowledge layer (spec R-K1, R-K4): the Graphify graph (`graphify-out/`) plus an OKF v0.2 bundle.

Mechanics: `bootstrap [check]`, `status`, `refresh`, `check`. Each is a skipped verdict when the layer is off
(`[knowledge] enabled = false` or CREWFORGE5_KNOWLEDGE=off). Bootstrap is check-only unless `[knowledge] auto_install`
is true: without it, local builds (`.graphifyignore`, the graph, the bundle) still run, but no tool is installed.

The bundle (`index.md`, `features/`, `modules/`) is cc_sdlc's `sdlc/knowledge/` when that exists (D2: shared, never
a second copy; there CrewForge5 writes only its own feature concepts and the Features block of the index, and leaves
modules to cc_sdlc), else `<home>/knowledge/`. Graphify, uv and npm are subprocesses; nothing here imports them.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import platform
import re
import shutil
from pathlib import Path

from . import artifacts as a
from . import project as p
from .project import StepFailed, StepSkipped, fail

SKIPPED = {"ok": True, "skipped": "knowledge disabled"}
SHARED = "sdlc/knowledge"  # cc_sdlc's bundle (spec D2)
STATE = ".crewforge5-state.json"  # our own state file, so a shared bundle's .state.json is never touched
FENCE = "---"
BAD = re.compile(r"[:#\[\]{}\",']|^\s|\s$|^[-?&*!|>%@`]")
NUMBERISH = re.compile(r"^[-+]?(\d[\d_]*\.?\d*([eE][-+]?\d+)?|\.\d+)$")
BUNDLE_OK = re.compile(r"^[A-Za-z0-9._][A-Za-z0-9._/-]*$")
BUILT_AT = re.compile(r'"built_at_commit"\s*:\s*"([0-9a-f]{7,40})"')
DIRS = ("features", "modules", "hubs", "lessons", "bands")  # the OKF directories an index lists (cc_sdlc writes all five)


class Unparseable(ValueError):
    """The YAML subset reader met a line it does not understand."""


# --- YAML subset: scalars, flat lists, {k: v} maps and lists of maps; everything OKF emits ---


def scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    plain = text and not BAD.search(text) and not NUMBERISH.match(text) and text not in ("true", "false", "null")
    return text if plain else json.dumps(text)


def flow(value) -> str:
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{key}: {scalar(v)}" for key, v in value.items()) + " }"
    if isinstance(value, list):
        return "[" + ", ".join(flow(v) for v in value) + "]"
    return scalar(value)


def dump_frontmatter(data: dict) -> str:
    lines = [FENCE]
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            lines.append(f"{key}:")
            lines += [f"  - {flow(v)}" for v in value]
        else:
            lines.append(f"{key}: {flow(value)}")
    return "\n".join([*lines, FENCE]) + "\n"


def read_scalar(text: str):
    text = text.strip()
    if text.startswith('"'):
        try:
            return json.loads(text)
        except json.JSONDecodeError as err:
            raise Unparseable(text) from err
    if text.startswith("'") and text.endswith("'") and len(text) >= 2:
        return text[1:-1]
    if text in ("true", "false"):
        return text == "true"
    if re.fullmatch(r"[-+]?\d+", text):
        return int(text)
    return text


def split_flow(text: str) -> list[str]:
    """Top-level comma split that respects quotes and nested brackets."""
    parts, depth, quote, start = [], 0, None, 0
    for i, ch in enumerate(text):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [part for part in (part.strip() for part in parts) if part]


def read_flow(text: str):
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        out = {}
        for item in split_flow(text[1:-1]):
            key, sep, value = item.partition(":")
            if not sep:
                raise Unparseable(item)
            out[key.strip()] = read_flow(value)
        return out
    if text.startswith("[") and text.endswith("]"):
        return [read_flow(item) for item in split_flow(text[1:-1])]
    if text.startswith(("[", "{")):
        raise Unparseable(text)
    return read_scalar(text)


def parse_frontmatter(block: str) -> dict:
    """The subset reader; on a line it cannot read, `_raw` holds the block and `type` survives if present."""
    out: dict = {}
    try:
        key = None
        for line in block.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line.startswith("  - ") and key:
                out.setdefault(key, []).append(read_flow(line[4:]))
                continue
            name, sep, value = line.partition(":")
            if not sep or name != name.strip() or not name:
                raise Unparseable(line)
            key = name
            out[key] = read_flow(value) if value.strip() else []
    except Unparseable:
        found = re.search(r"^type:\s*(.+)$", block, re.MULTILINE)
        return {"_raw": block, **({"type": read_scalar(found.group(1))} if found else {})}
    return out


def split_document(text: str) -> tuple[dict, str]:
    if not text.startswith(FENCE + "\n"):
        return {}, text
    end = text.find("\n" + FENCE + "\n", len(FENCE))
    if end < 0:
        return {}, text
    body = text[end + len(FENCE) + 2 :]
    return parse_frontmatter(text[len(FENCE) + 1 : end + 1]), body.removeprefix("\n")


# --- the layer switch, paths and small helpers ---


def enabled(root: Path) -> bool:
    return p.enabled(root, "knowledge")


def when_enabled(fn):
    """Gate a public mechanic on the layer being on; off, it returns the skipped verdict."""

    @functools.wraps(fn)
    def inner(root: Path, *args, **kwargs):
        return fn(root, *args, **kwargs) if enabled(root) else dict(SKIPPED)

    return inner


def cfg(root: Path) -> dict:
    return p.config(root)["knowledge"]


def bundle_rel(root: Path) -> str:
    """`[knowledge] bundle`, else cc_sdlc's `sdlc/knowledge/` when present (D2), else `<home>/knowledge`."""
    configured = str(cfg(root)["bundle"]).strip()
    if configured:
        if not BUNDLE_OK.match(configured) or ".." in Path(configured).parts or configured.endswith("/"):
            fail(f"[knowledge] bundle {configured!r} must be a relative path made of letters, digits, `.`, `_`, `-` and `/`, without `..`")
        return configured
    if (root / SHARED).is_dir():
        return SHARED
    return f"{p.rel(root, p.home(root))}/knowledge"


def bundle_dir(root: Path) -> Path:
    return root / bundle_rel(root)


def shared(root: Path) -> bool:
    return bundle_rel(root) == SHARED


def graph_path(root: Path) -> Path:
    return root / "graphify-out" / "graph.json"


def skill_path() -> Path:
    return p.claude_dir() / "skills" / "graphify" / "SKILL.md"


def read_state(root: Path) -> dict:
    """Our state file, or `{"_error": reason}` when it exists but cannot be read (a merge conflict, say)."""
    path = bundle_dir(root) / STATE
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
    except ValueError as err:
        return {"_error": f"{STATE} is not valid JSON ({err})"}
    return data if isinstance(data, dict) else {"_error": f"{STATE} is not a JSON object"}


def load_graph(root: Path) -> dict:
    graph = p.read_json(graph_path(root), {}) or {}
    return {"nodes": graph.get("nodes", []), "links": graph.get("links", []), **{k: v for k, v in graph.items() if k not in ("nodes", "links")}}


def graph_commit(root: Path) -> str | None:
    path = graph_path(root)
    match = BUILT_AT.search(path.read_text()) if path.exists() else None
    return match.group(1) if match else None


def behind(root: Path, since: str | None) -> int | None:
    """Commits from `since` to HEAD; None when git cannot resolve `since` (shallow clone, rebase, foreign history)."""
    if not since:
        return None
    result = p.run_git(root, "rev-list", "--count", f"{since}..HEAD")
    return int(result.stdout.strip() or 0) if result.returncode == 0 else None


# --- bootstrap: check, build locally, and install only with [knowledge] auto_install ---

UV_INSTALL = {
    "posix": ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
    "windows": ["powershell", "-ExecutionPolicy", "ByPass", "-c", "irm https://astral.sh/uv/install.ps1 | iex"],
}
GRAPHIFY_INSTALL = ["uv", "tool", "install", "graphifyy"]
SKILL_INSTALL = ["graphify", "install", "--platform", "claude"]


def uv_install_command(system: str | None = None) -> list[str]:
    system = system or platform.system()
    return UV_INSTALL["windows" if system.lower().startswith("win") else "posix"]


def find_uv() -> str | None:
    """uv on PATH, else where astral's installer puts it."""
    if found := shutil.which("uv"):
        return found
    for candidate in (Path.home() / ".local" / "bin", Path.home() / ".cargo" / "bin"):
        exe = candidate / ("uv.exe" if os.name == "nt" else "uv")
        if exe.exists():
            return str(exe)
    return None


def need(tool: str) -> None:
    if not shutil.which(tool):
        raise StepSkipped(f"{tool} not on PATH")


def write_ignore(root: Path, conf: dict) -> str:
    (root / ".graphifyignore").write_text("".join(f"{line}\n" for line in conf["ignore"]))
    return ".graphifyignore from [knowledge] ignore"


def build_graph(root: Path, conf: dict) -> str:
    need("graphify")
    return p.ran(root, ["graphify", "update", "."], graph_path(root).exists)


def bundle_present(root: Path, conf: dict) -> bool:
    """The bundle counts only when it was built from the graph that exists now."""
    return (bundle_dir(root) / "index.md").exists() and read_state(root).get("graph_commit") == graph_commit(root)


def build_bundle(root: Path, conf: dict) -> str:
    if why := update_graph(root):
        raise StepFailed(why)
    refresh(root)
    return bundle_rel(root)


def steps():
    """(name, present?(root, conf), run(root, conf) -> detail, kind, detail when present). `install` steps run only with
    auto_install; `build` steps are local writes. present? may raise StepSkipped when the step does not apply here."""
    from . import docs, packs  # both import this module

    return (
        ("uv", lambda r, c: find_uv() is not None, lambda r, c: p.ran(r, uv_install_command(), lambda: find_uv() is not None), "install", "uv"),
        ("graphify", lambda r, c: shutil.which("graphify") is not None, lambda r, c: p.ran(r, GRAPHIFY_INSTALL, lambda: shutil.which("graphify") is not None), "install", "graphify on PATH"),
        ("skill", lambda r, c: skill_path().exists(), lambda r, c: (need("graphify"), p.ran(r, SKILL_INSTALL, skill_path().exists))[1], "install", "Graphify Claude skill"),
        ("graphifyignore", lambda r, c: (r / ".graphifyignore").exists(), write_ignore, "build", ".graphifyignore"),
        ("graph", lambda r, c: graph_path(r).exists(), build_graph, "build", "graphify-out/graph.json"),
        ("repomix", packs.repomix_present, packs.install_repomix, "install", "repomix on PATH"),
        ("archify", docs.archify_present, docs.install_archify, "install", "Archify skill"),
        ("bundle", bundle_present, build_bundle, "build", "OKF bundle"),
    )


INSTALL_HINT = {"uv": " ".join(UV_INSTALL["posix"][2:]), "graphify": " ".join(GRAPHIFY_INSTALL), "skill": " ".join(SKILL_INSTALL), "repomix": "npm i -g repomix"}
OPTIONAL = {"repomix", "archify"}  # packs and documents are layers on top; the graph and bundle never wait for them


@when_enabled
def bootstrap(root: Path, check: bool = False) -> dict:
    """Idempotent: a healthy project spawns no subprocess. `check` runs nothing at all."""
    conf = cfg(root)
    out: list[dict] = []
    for name, present, run_step, kind, detail in steps():
        try:
            if found := present(root, conf):
                state, detail = "present", (found if isinstance(found, str) else detail)
            elif check or (kind == "install" and not conf["auto_install"]):
                state = "missing"
                detail = f"install: {INSTALL_HINT[name]}" if name in INSTALL_HINT else "run `crewforge5 knowledge bootstrap`"
            else:
                state, detail = ("installed" if kind == "install" else "built"), run_step(root, conf)
        except StepSkipped as why:
            state, detail = "skipped", str(why)
        except StepFailed as err:
            state, detail = "failed", str(err)
        out.append({"name": name, "state": state, "detail": detail})
    broken = [s for s in out if s["state"] == "failed" and s["name"] not in OPTIONAL]
    missing = [s["name"] for s in out if s["state"] == "missing" and s["name"] not in OPTIONAL]
    index = f"{bundle_rel(root)}/index.md"
    verdict = {"ok": not broken and not missing, "mode": "check" if check else "install" if conf["auto_install"] else "build", "steps": out, "bundle": bundle_rel(root), "shared": shared(root)}
    if broken:
        verdict["reason"] = "; ".join(f"bootstrap step {s['name']} failed: {s['detail']}" for s in broken)
    elif missing:
        verdict["reason"] = "missing: " + ", ".join(missing) + " (install them, or set [knowledge] auto_install = true and rerun `crewforge5 knowledge bootstrap`)"
    verdict["next"] = f"read {index} before raw files" if verdict["ok"] else "carry on without the graph: read the files directly and grep; say once which tools are missing"
    return verdict


# --- status ---


@when_enabled
def status(root: Path) -> dict:
    conf, state = cfg(root), read_state(root)
    gcommit = graph_commit(root)
    graph = {"commit": gcommit, "behind": behind(root, gcommit)}
    bundle = {"path": bundle_rel(root), "shared": shared(root), "commit": state.get("commit"), "behind": behind(root, state.get("commit")), "concepts": len(concept_files(root))}
    reasons = []
    if gcommit is None:
        reasons.append("graphify-out/graph.json missing or without built_at_commit; run `crewforge5 knowledge bootstrap`")
    elif graph["behind"] is None:
        reasons.append(f"graph commit {gcommit[:12]} is not in this history; run `graphify update . --force`")
    elif graph["behind"] > conf["max_behind"]:
        reasons.append(f"graph is {graph['behind']} commits behind HEAD (max_behind {conf['max_behind']}); run `crewforge5 knowledge refresh`")
    if "_error" in state:
        reasons.append(f"{bundle['path']}/{STATE} unreadable ({state['_error']}); run `crewforge5 knowledge refresh`")
    elif bundle["commit"] is None:
        reasons.append(f"{bundle['path']} not built by CrewForge5 yet; run `crewforge5 knowledge refresh`")
    elif bundle["behind"] is None or bundle["behind"] > conf["max_behind"]:
        reasons.append(f"bundle is behind HEAD (max_behind {conf['max_behind']}); run `crewforge5 knowledge refresh`")
    verdict = {"ok": not reasons, "graph": graph, "bundle": bundle, "reasons": reasons, "next": f"read {bundle['path']}/index.md"}
    if reasons:
        verdict.update(reason="; ".join(reasons), next="crewforge5 knowledge refresh")
    return verdict


# --- refresh: graph.json + feature artifacts -> OKF bundle ---


def is_code(node: dict) -> bool:
    if "file_type" in node:
        return node["file_type"] == "code"
    return node.get("_origin") == "ast"


def communities(graph: dict, conf: dict) -> list[dict]:
    """Graphify code communities big enough for a Module concept, with a stable slug each."""
    groups: dict[int, list[dict]] = {}
    for node in graph["nodes"]:
        if node.get("community") is not None and node.get("source_file"):
            groups.setdefault(node["community"], []).append(node)
    out, taken = [], set()
    for cid in sorted(groups):
        nodes = groups[cid]
        if sum(is_code(n) for n in nodes) < conf["min_community_nodes"]:
            continue
        name = next((n["community_name"] for n in nodes if n.get("community_name")), f"Community {cid}")
        slug = a.slugify(name) or f"community-{cid}"
        slug = slug if slug not in taken else f"{slug}-{cid}"
        taken.add(slug)
        out.append({"cid": cid, "name": name, "slug": slug, "files": sorted({n["source_file"] for n in nodes}), "nodes": nodes})
    return out


def section(heading: str, lines: list[str], empty: str = "none") -> str:
    return f"# {heading}\n" + ("\n".join(lines) if lines else f"- {empty}") + "\n\n"


def concept(path: str, type_: str, title: str, description: str, resource: str, tags: list[str], sources: list[str], body: str) -> dict:
    front = {"type": type_, "title": title.strip(), "description": description[:200].strip(), "resource": resource, "tags": tags}
    return {"path": path, "front": front, "sources": sources, "body": "\n".join(line.rstrip() for line in body.rstrip("\n").splitlines()) + "\n"}


def module_concepts(graph: dict, comms: list[dict]) -> list[dict]:
    by_node = {n["id"]: c for c in comms for n in c["nodes"]}
    deps: dict[str, set[str]] = {c["slug"]: set() for c in comms}
    for edge in graph["links"]:
        src, dst = by_node.get(edge.get("source")), by_node.get(edge.get("target"))
        if src is not None and dst is not None and src is not dst and edge.get("confidence", "EXTRACTED") == "EXTRACTED":
            deps[src["slug"]].add(dst["slug"])
    names = {c["slug"]: c["name"] for c in comms}
    out = []
    for c in comms:
        symbols = sorted(c["nodes"], key=lambda n: (n["source_file"], str(n.get("source_location", ""))))
        out.append(
            concept(
                f"modules/{c['slug']}.md",
                "Module",
                c["name"],
                f"Graphify community {c['cid']}: " + ", ".join(c["files"]),
                os.path.commonpath(c["files"]) if len(c["files"]) > 1 else str(Path(c["files"][0]).parent),
                ["module", "graphify"],
                c["files"],
                section("Files", [f"- `{f}`" for f in c["files"]])
                + section("Symbols", [f"- {n.get('label', n['id'])} ({n['source_file']}:{n.get('source_location', '')})" for n in symbols])
                + section("Depends on", [f"- [{names[d]}](/modules/{d}.md)" for d in sorted(deps[c["slug"]])], "no EXTRACTED edges to other modules"),
            )
        )
    return out


def feature_concepts(root: Path) -> list[dict]:
    from . import build, docs, stages  # build imports stages; docs imports this module

    out = []
    for feature in p.features(root):
        intent = (feature / "intent.md").read_text()
        spec = feature / "spec.md"
        rel = p.rel(root, feature)
        found = a.sections(intent)
        out.append(
            concept(
                f"features/{feature.name}.md",
                "Feature",
                a.title(intent) or feature.name,
                (found.get("Problem", "").strip().splitlines() or [feature.name])[0],
                rel,
                ["feature", "crewforge5", a.status(intent) or "draft"],
                [f"{rel}/{n}" for n in ("intent.md", "spec.md", "plan.md", "review.md") if (feature / n).exists()],
                section("Problem", [found.get("Problem", "").strip()])
                + section("Outcome", [found.get("Proposed outcome", "").strip()])
                + section("Requirements", [a.sections(spec.read_text()).get("Requirements", "").strip()] if spec.exists() else [], "spec.md not written yet")
                + section("Files", [f"- `{f}`" for f in build.planned(feature)], "plan.md not written yet")
                + section("Status", [f"- {name}: {state}" for name, state in stages.state(feature).items()])
                + section("Documents", docs.documents(root, feature)),
            )
        )
    return out


def digest(root: Path, rel: str) -> str:
    path = root / rel
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else "missing"


def render_concept(root: Path, c: dict, commit: str) -> str:
    front = {
        **c["front"],
        "status": "draft",
        "generated": {"by": f"crewforge5/{plugin_version()}", "at": p.now_iso()},
        "source_commit": commit,
        "sources": [{"resource": s, "digest": digest(root, s)} for s in c["sources"]],
    }
    return dump_frontmatter(front) + "\n" + c["body"]


RUN_KEYS = ("generated", "source_commit", "_raw")


def same_content(existing: str, new: str) -> bool:
    """Equal but for what each run rewrites (generation stamp, commit): an unchanged concept is never rewritten."""
    (old_front, old_body), (new_front, new_body) = split_document(existing), split_document(new)
    strip = lambda f: {k: v for k, v in f.items() if k not in RUN_KEYS}  # noqa: E731
    return "_raw" not in old_front and strip(old_front) == strip(new_front) and old_body == new_body


@functools.cache
def plugin_version() -> str:
    return (p.read_json(p.PLUGIN_ROOT / ".claude-plugin" / "plugin.json", {}) or {}).get("version", "0")


def title_of(path: Path) -> tuple[str, str]:
    front, _ = split_document(path.read_text())
    return str(front.get("title") or path.stem), str(front.get("description") or "")


def index_lines(home: Path, folder: str, basename: bool) -> str:
    entries = sorted((title_of(f), f) for f in (home / folder).glob("*.md") if f.name != "index.md") if (home / folder).is_dir() else []
    lines = [f"* [{t}]({f.name if basename else f'{folder}/{f.name}'}) - {d}" for (t, d), f in sorted(entries, key=lambda e: e[0][0].lower())]
    return "\n".join(lines) if lines else "* none yet"


FEATURES_BLOCK = re.compile(r"^# Features\n.*?(?=\n\n# |\Z)", re.DOTALL | re.MULTILINE)


def write_indexes(root: Path, home: Path, own: tuple[str, ...]) -> None:
    """Sub-indexes for the folders we write; the top index lists every OKF folder on disk. In a shared bundle only the
    Features block of cc_sdlc's index.md is replaced, so its other sections and wording survive."""
    for folder in own:
        (home / folder).mkdir(parents=True, exist_ok=True)
        (home / folder / "index.md").write_text(f"# {folder.capitalize()}\n\n" + index_lines(home, folder, basename=True) + "\n")
    top = home / "index.md"
    if shared(root) and top.exists():
        block = "# Features\n" + index_lines(home, "features", basename=False)
        text = top.read_text()
        top.write_text(FEATURES_BLOCK.sub(lambda _: block, text, count=1) if FEATURES_BLOCK.search(text) else text.rstrip("\n") + "\n\n" + block + "\n")
        return
    folders = [d for d in DIRS if d in own or (home / d).is_dir()]
    parts = "\n\n".join(f"# {d.capitalize()}\n" + index_lines(home, d, basename=False) for d in folders)
    top.write_text(a.render(p.TEMPLATES / "knowledge" / "index.md", title=f"{root.name} knowledge", sections=parts))


def update_graph(root: Path) -> str | None:
    """Rebuild a graph that is behind HEAD when Graphify is on PATH; the failure reason, or None."""
    if not shutil.which("graphify") or graph_commit(root) == p.head(root):
        return None
    result = p.run_cmd(root, ["graphify", "update", "."])
    return f"graphify update . exited {result.returncode}: {result.stderr.strip()[-200:]}" if result.returncode else None


@when_enabled
def refresh(root: Path) -> dict:
    """Rebuild a behind graph (when Graphify is on PATH), then write the concepts and indexes; unchanged ones stay put."""
    conf, home = cfg(root), bundle_dir(root)
    commit = p.head(root)
    if why := update_graph(root):
        fail(why)
    graph = load_graph(root)
    is_shared = shared(root)
    concepts = feature_concepts(root) + ([] if is_shared else module_concepts(graph, communities(graph, conf)))
    home.mkdir(parents=True, exist_ok=True)
    written, kept, foreign = [], 0, []
    for c in concepts:
        path = home / c["path"]
        if is_shared and path.exists() and split_document(path.read_text())[0].get("resource") != c["front"]["resource"]:
            foreign.append(c["path"])  # a cc_sdlc feature of the same slug: never overwritten
            continue
        text = render_concept(root, c, commit)
        if path.exists() and same_content(path.read_text(), text):
            kept += 1
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(c["path"])
    write_indexes(root, home, ("features",) if is_shared else ("features", "modules"))
    p.write_json(home / STATE, {"commit": commit, "graph_commit": graph_commit(root), "ts": p.now_iso()})
    return {"ok": True, "bundle": bundle_rel(root), "shared": is_shared, "concepts": len(concepts) - len(foreign), "written": written, "unchanged": kept, "skipped_foreign": foreign, "next": f"read {bundle_rel(root)}/index.md"}


# --- check: OKF conformance ---


def concept_files(root: Path) -> list[Path]:
    home = bundle_dir(root)
    return sorted(f for f in home.rglob("*.md") if f.name not in ("index.md", "log.md")) if home.exists() else []


@when_enabled
def check(root: Path) -> dict:
    """OKF v0.2 conformance: every concept has a parseable frontmatter block with a non-empty `type`."""
    home = bundle_dir(root)
    findings = []
    for path in concept_files(root):
        rel = str(path.relative_to(home))
        front, _ = split_document(path.read_text())
        if not front:
            findings.append(f"{rel}: no parseable YAML frontmatter block")
        elif "_raw" in front and "type" not in front:
            findings.append(f"{rel}: frontmatter is not parseable YAML")
        elif not isinstance(front.get("type"), str) or not front["type"].strip():
            findings.append(f"{rel}: missing or empty `type`")
    verdict = {"ok": not findings, "conformance": findings, "concepts": len(concept_files(root)), "bundle": bundle_rel(root), "next": f"read {bundle_rel(root)}/index.md"}
    if findings:
        verdict.update(reason=f"{len(findings)} conformance finding(s): " + "; ".join(findings[:3]), next="crewforge5 knowledge refresh")
    return verdict
