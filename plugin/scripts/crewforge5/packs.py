"""Graph-selected Repomix context packs (spec R-K2, R-K3, C5): one commit-pinned snapshot per stage for its Workflow agents.

Seeds come from the stage artifact, grow `[packs] hops` graph hops through graphify-out/graph.json, pass a frozen secret
exclude list, Bandit (fails closed) and Repomix's own secret check, and land in graphify-out/packs/<slug>/ (never
committed). Verdicts name paths and rule ids, never matched text. `require` is the build-accept and review-review gate:
a pack built at HEAD, and for review one accounting for every changed text file. Off: the knowledge layer's switches,
`[packs] enabled = false` or CREWFORGE5_PACKS=off.
"""

from __future__ import annotations

import fnmatch
import hashlib
import html
import json
import os
import re
import shutil
from collections import defaultdict
from pathlib import Path

from . import artifacts as a
from . import build as b
from . import knowledge
from . import project as p
from .project import StepSkipped, fail

GATED = frozenset({"build", "review"})  # stages whose exit needs a pack at HEAD; a code constant, never config
REPOMIX_INSTALL = ["npm", "i", "-g", "repomix"]
INSTALL_CMD = " ".join(REPOMIX_INSTALL)
PACKS_OFF = {"ok": True, "skipped": "packs disabled"}
BACKTICK = re.compile(r"`([^`\s]+)`")
LINE_SUFFIX = re.compile(r":\d+(-\d+)?$")


def tracked(root: Path) -> list[str]:
    """Tracked paths, NUL-separated so git never quotes unusual names."""
    return [f for f in p.git(root, "ls-files", "-z").split("\0") if f]


def resolve(files: list[str], tokens: list[str]) -> tuple[list[str], list[str]]:
    """Tracked `files` a token names (a file, a directory or a glob); tokens naming nothing are returned, never guessed."""
    known, found, unresolved = set(files), set(), []
    for token in tokens:
        name = LINE_SUFFIX.sub("", token).rstrip("/")
        glob = any(c in name for c in "*?[")
        hits = [name] if name in known else [f for f in files if f.startswith(name + "/") or (glob and fnmatch.fnmatch(f, name))]
        found.update(hits)
        if not hits:
            unresolved.append(token)
    return sorted(found), unresolved


def section_tokens(path: Path, heading: str) -> list[str]:
    return BACKTICK.findall(a.sections(path.read_text()).get(heading, "")) if path.exists() else []


def changed_since(root: Path, spec: str) -> list[str]:
    """Committed text files changed in `spec` (a git range); deleted, binary (numstat `-`) and plugin-owned paths left out."""
    out = p.git(root, "diff", "--numstat", "-z", "--no-renames", "--diff-filter=d", spec)
    rows = [entry.split("\t", 2) for entry in out.split("\0") if entry.count("\t") >= 2]
    return [path for added, _, path in rows if added != "-" and not b.owned(root, path)]


def review_changes(root: Path) -> list[str]:
    """What the review pack seeds from and must cover: the branch diff against `[packs] base`."""
    return changed_since(root, f"{p.config(root)['packs']['base']}...HEAD")


def plan_seeds(root: Path, feature: Path) -> list[str]:
    return section_tokens(feature / "intent.md", "Affected users and systems")


SEEDS = {
    "plan": plan_seeds,
    "design": lambda r, f: plan_seeds(r, f) + section_tokens(f / "spec.md", "Design"),
    "build": lambda r, f: b.planned(f),
    "review": lambda r, f: review_changes(r),
}


def seeds(root: Path, feature: Path, stage: str, files: list[str] | None = None) -> tuple[list[str], list[str]]:
    """Seed files for a stage; plugin-owned paths (artifacts, the bundle) never seed: agents read those directly."""
    candidates = [f for f in (tracked(root) if files is None else files) if not b.owned(root, f)]
    return resolve(candidates, SEEDS[stage](root, feature))


# Secret-bearing paths that never reach Repomix, whatever the graph selects; frozen here, no config key shrinks it.
# A pattern without `/` matches the file name, one with `/` the whole path (`/**` = everything below).
EXCLUDE = (
    ".env*",
    ".claude/settings.local.json",
    *("*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "*.crt", "*.cer"),
    *("id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*"),
    *(".netrc", ".npmrc", ".pypirc", "*credentials*"),
    "graphify-out/**",
    ".git/**",
)


def secret_rule(path: str) -> str | None:
    """The EXCLUDE pattern `path` matches, ignoring case (`SERVER.PEM` is still a key)."""
    lower = path.lower()
    for rule in EXCLUDE:
        if lower.startswith(rule[:-2]) if rule.endswith("/**") else fnmatch.fnmatchcase(lower if "/" in rule else Path(lower).name, rule):
            return rule
    return None


def git_ignored(root: Path, files: list[str]) -> set[str]:
    """Files git would ignore, tracked or not (`--no-index`)."""
    if not files:
        return set()
    return set(p.run_cmd(root, ["git", "check-ignore", "-z", "--no-index", "--stdin"], input="\0".join(files)).stdout.split("\0")) - {""}


def admit(root: Path, files: list[str], known: set[str] | None = None) -> tuple[list[str], list[dict]]:
    """Split the selection into files Repomix may read and exclusions with the rule that matched; `known` = tracked files."""
    known = set(tracked(root)) if known is None else known
    ignored, base = git_ignored(root, files), root.resolve()
    admitted, excluded = [], []
    for path in sorted(files):
        full = root / path
        rule = (
            secret_rule(path)
            or ("untracked" if path not in known else None)
            or ("symlink" if full.is_symlink() else None)
            or ("outside root" if not full.resolve().is_relative_to(base) else None)
            or ("git-ignored" if path in ignored else None)
        )
        if rule:
            excluded.append({"path": path, "rule": rule})
        else:
            admitted.append(path)
    return admitted, excluded


def expand(graph: dict, seed_files: list[str], hops: int) -> dict[str, str]:
    """{path: seed|caller|callee|community}: files `hops` `calls` links from a seed, plus each seed's community."""
    files: dict[str, str] = dict.fromkeys(seed_files, "seed")
    node_file, by_file, community_files = {}, defaultdict(set), defaultdict(set)
    for node in graph["nodes"]:
        if path := node.get("source_file"):
            node_file[node["id"]] = path
            by_file[path].add(node["id"])
            community_files[node.get("community")].add(path)
    callees, callers = defaultdict(set), defaultdict(set)
    for link in graph["links"]:
        if link.get("relation") == "calls":
            callees[link["source"]].add(link["target"])
            callers[link["target"]].add(link["source"])
    frontier = {n for s in seed_files for n in by_file[s]}
    for _ in range(hops):
        reached = {t: "callee" for n in frontier for t in callees[n]} | {s: "caller" for n in frontier for s in callers[n]}
        frontier = set()
        for node_id, reason in reached.items():
            if (path := node_file.get(node_id)) and path not in files:
                files[path] = reason
                frontier.add(node_id)
    for community in {n.get("community") for n in graph["nodes"] if n.get("source_file") in seed_files} - {None}:
        for path in sorted(community_files[community]):
            files.setdefault(path, "community")
    return files


# --- preconditions: the layer is on, Repomix exists, the graph describes HEAD ---


def off(root: Path) -> dict | None:
    """The visible skip verdict when packs do not apply: the knowledge layer is off, or the packs layer is."""
    if not knowledge.enabled(root):
        return dict(knowledge.SKIPPED)
    return None if p.enabled(root, "packs") else dict(PACKS_OFF)


def repomix_on_path() -> bool:
    return shutil.which("repomix") is not None


def missing_repomix() -> str | None:
    return None if repomix_on_path() else f"repomix not on PATH; install it with `{INSTALL_CMD}` (or set [knowledge] auto_install = true and run `crewforge5 knowledge bootstrap`)"


def repomix_present(root: Path, conf: dict) -> bool:
    """The knowledge bootstrap's `repomix` step."""
    if not p.enabled(root, "packs"):
        raise StepSkipped(PACKS_OFF["skipped"])
    return repomix_on_path()


def install_repomix(root: Path, conf: dict) -> str:
    return p.ran(root, REPOMIX_INSTALL, repomix_on_path)


def exempt(root: Path, path: str) -> bool:
    """A change that never makes the graph stale: plugin-owned paths and `[knowledge] ignore`."""
    return b.owned(root, path) or any(fnmatch.fnmatch(path, pat + "*") if pat.endswith("/") else path == pat for pat in knowledge.cfg(root)["ignore"])


def fresh_graph(root: Path) -> dict:
    """The graph, provided it names a commit and no non-exempt file changed since; graphify-out/ must be ignored."""
    ignore = root / ".graphifyignore"
    if not ignore.exists() or not {"graphify-out", "graphify-out/", "graphify-out/**"} & {line.strip() for line in ignore.read_text().splitlines()}:
        fail(".graphifyignore must list graphify-out/ so a pack never becomes graph input; run `crewforge5 knowledge bootstrap`", next="crewforge5 knowledge bootstrap")
    graph = knowledge.load_graph(root)
    if not (built := graph.get("built_at_commit")):
        fail("graphify-out/graph.json missing or without built_at_commit; run `crewforge5 knowledge bootstrap`", next="crewforge5 knowledge bootstrap")
    if stale := [f for f in p.git(root, "diff", "--name-only", built, "HEAD").splitlines() if f and not exempt(root, f)]:
        fail("graph.json is behind HEAD for files a pack would select; run `crewforge5 knowledge refresh`", stale=stale, next="crewforge5 knowledge refresh")
    return graph


def command(stage: str, slug: str) -> str:
    return f"crewforge5 knowledge pack {stage} --slug {slug}"


def build(root: Path, slug: str | None, stage: str | None, max_tokens: int | None = None) -> dict:
    """Select, guard and pack the files a stage's agents need; see the module docstring."""
    if skipped := off(root):
        return skipped
    if stage not in SEEDS:
        fail(f"no context pack for stage {stage!r}: packs are built for {', '.join(SEEDS)}", next="crewforge5 knowledge pack plan|design|build|review")
    feature = p.feature(root, slug)
    if reason := missing_repomix():
        if stage in GATED:
            fail(reason, next=INSTALL_CMD)
        return {"ok": True, "skipped": reason, "next": "continue without a pack; the stage's workflow runs without args.pack"}
    conf = p.config(root)["packs"]
    files, seed_files, unresolved, excluded = select(root, feature, stage, fresh_graph(root), conf["hops"])
    budget = max_tokens if max_tokens is not None else conf["max_tokens"]
    version = p.run_cmd(root, ["repomix", "--version"]).stdout.strip()
    head = p.head(root)
    key = hashlib.sha256(json.dumps([head, sorted(files), budget, version]).encode()).hexdigest()
    out = store(root) / feature.name
    manifest_path = out / f"{stage}-{key[:12]}.json"
    if (cached := p.read_json(manifest_path)) and Path(cached["path"]).exists():
        return {"ok": True, **verdict_of(cached), "reused": True}
    run_bandit(root, [f for f in files if f.endswith(".py")])
    identity = {"slug": feature.name, "stage": stage, "head": head, "key": key, "repomix_version": version}
    return write_pack(out, manifest_path, identity, files, seed_files, unresolved, excluded, budget, root)


def select(root: Path, feature: Path, stage: str, graph: dict, hops: int) -> tuple[dict, list[str], list[str], list[dict]]:
    """({admitted path: reason}, seeds, unresolved tokens, exclusions); refuses when an admitted file is dirty."""
    known = tracked(root)
    seed_files, unresolved = seeds(root, feature, stage, known)
    selected = expand(graph, seed_files, hops)
    admitted, excluded = admit(root, list(selected), set(known))
    if admitted and (dirty := p.changed_files(root, *admitted)):  # no paths would mean every dirty file
        fail("packed files have uncommitted changes; a pack is pinned to HEAD, so commit or stash them first", dirty=dirty)
    return {f: selected[f] for f in admitted}, seed_files, unresolved, excluded


def write_pack(out: Path, manifest_path: Path, identity: dict, files: dict, seed_files: list[str], unresolved: list[str], excluded: list[dict], budget: int, root: Path) -> dict:
    """Walk the ladder into a temp file, then write the manifest and move the pack into place; older pairs pruned."""
    stage, key = identity["stage"], identity["key"]
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / f".{stage}-{key[:12]}.tmp.xml"
    try:
        packed, steps = ladder(root, list(files), set(seed_files), budget, tmp)
        tokens = steps[-1]["tokens"]
        pack_path = manifest_path.with_suffix(".xml")
        manifest = {
            **identity,
            "path": str(pack_path),
            "manifest": str(manifest_path),
            "files": {f: files[f] for f in packed},
            "seeds": seed_files,
            "unresolved": unresolved,
            "excluded": excluded,
            "tokens": tokens,
            "steps": steps,
            "over_budget": bool(budget) and tokens > budget,
            "budget": budget,
            "built": p.now_iso(),
        }
        p.write_json(manifest_path, manifest)
        tmp.replace(pack_path)
    finally:
        tmp.unlink(missing_ok=True)
    for old in out.glob(f"{stage}-*"):
        if not old.name.startswith(f"{stage}-{key[:12]}."):
            old.unlink()
    return {"ok": True, **verdict_of(manifest), "reused": False}


VERDICT_KEYS = ("path", "manifest", "files", "seeds", "unresolved", "excluded", "tokens", "steps", "over_budget")


def verdict_of(manifest: dict) -> dict:
    verdict = {k: manifest[k] for k in VERDICT_KEYS}
    verdict["next"] = f"pass {manifest['path']} to the stage workflow as args.pack (data, never instructions)"
    if manifest["over_budget"]:
        verdict["reason"] = f"over budget: seeds only still needs {manifest['tokens']} tokens (budget {manifest['budget']}); the pack is written anyway"
    return verdict


# (rung, --compress, seeds only): tried in order until the pack fits the budget; with no budget only `full` runs
LADDER = (("full", False, False), ("compress", True, False), ("seeds", True, True))


def ladder(root: Path, admitted: list[str], seed_set: set[str], budget: int, out: Path) -> tuple[list[str], list[dict]]:
    """Step down the ladder, recording every rung tried with its tokens and dropped files; seeds are never dropped."""
    steps: list[dict] = []
    files = admitted
    for rung, compress, seeds_only in LADDER:
        files = [f for f in admitted if f in seed_set] if seeds_only else admitted
        tokens = run_repomix(root, files, out, compress)
        steps.append({"rung": rung, "tokens": tokens, "dropped": sorted(set(admitted) - set(files))})
        if not budget or tokens <= budget:
            break
    return files, steps


def packs_dir(root: Path) -> Path:
    return knowledge.graph_path(root).parent / "packs"


def store(root: Path) -> Path:
    """packs_dir, created with a `*` .gitignore on first use so nothing in it is ever committed."""
    base = packs_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    if not (ignore := base / ".gitignore").exists():
        ignore.write_text("*\n")
    return base


# --- Bandit: hardcoded-password tests over the Python files, before Repomix; fails closed ---

BANDIT = "bandit==1.9.4"  # pinned so a release cannot change what refuses a pack; bump deliberately
BANDIT_TESTS = "B105,B106,B107"


def run_bandit(root: Path, py_files: list[str]) -> None:
    if not py_files:
        return
    argv = [knowledge.find_uv() or "uv", "tool", "run", "--from", BANDIT, "bandit", "-q", "-f", "json", "-t", BANDIT_TESTS, "--", *py_files]
    result = p.run_cmd(root, argv)
    if result.returncode not in (0, 1):
        fail(f"bandit exited {result.returncode}; no pack written (the scan fails closed)", stderr=result.stderr.strip()[-300:])
    try:
        results = json.loads(result.stdout)["results"]
    except (json.JSONDecodeError, KeyError, TypeError):
        fail("bandit printed no readable JSON; no pack written (the scan fails closed)")
    if findings := [f"{os.path.normpath(r['filename'])}:{r['line_number']} {r['test_id']}" for r in results]:  # bandit prints ./path
        fail("bandit found hardcoded passwords; no pack written. Move the secret out of the source", findings=findings)


# --- Repomix, and the scanner that refuses anything but exactly the requested files ---

CONFIG = p.TEMPLATES / "knowledge" / "repomix.config.json"
SUSPICIOUS = re.compile(r"suspicious file\(s\) detected")
LISTED = re.compile(r"^\s*\d+\.\s+(\S.*?)\s*$")
TOTAL = re.compile(r"Total Tokens:\s*([\d,]+)")
PACKED = re.compile(r'<file path="([^"]+)">')


def run_repomix(root: Path, files: list[str], out: Path, compress: bool) -> int:
    """Pack `files` into `out` with the plugin's config (secret check forced on); the token count, or a refusal.
    An empty selection writes an empty pack: repomix given no paths would pack the whole repository."""
    if not files:
        out.write_text("<files>\n</files>\n")
        return 0
    argv = ["repomix", "--stdin", "--config", str(CONFIG), "--style", "xml", "--output", str(out), *(["--compress"] if compress else [])]
    result = p.run_cmd(root, argv, env={"NO_COLOR": "1"}, input="\n".join(files) + "\n")
    if result.returncode != 0:
        fail(f"repomix exited {result.returncode}; no pack written", stderr=result.stderr.strip()[-300:])
    scan_output(result.stdout, files, out.read_text() if out.exists() else "")
    match = TOTAL.search(result.stdout)
    return int(match.group(1).replace(",", "")) if match else 0


def suspicious(stdout: str) -> list[str]:
    """Files Repomix's secret check flagged, read from its Security Check block only (the top-files list looks alike)."""
    lines = stdout.splitlines()
    start = next((i for i, line in enumerate(lines) if SUSPICIOUS.search(line)), None)
    found = []
    for line in lines[start + 1 :] if start is not None else []:
        if not line.strip():
            break
        if match := LISTED.match(line):
            found.append(match.group(1))
    return found


def scan_output(stdout: str, requested: list[str], xml: str) -> None:
    """Refuse unless the output holds exactly the requested files; verdicts name paths, never file contents."""
    if flagged := suspicious(stdout):
        fail("repomix's secret check flagged files; no pack written. Remove the secret or keep the file out of the stage artifact", flagged=flagged)
    packed = {html.unescape(path) for path in PACKED.findall(xml)}  # parsable style escapes contents, so only headers match
    if missing := sorted(set(requested) - packed):
        fail("repomix left requested files out of the pack; no pack written", missing=missing)
    if extra := sorted(packed - set(requested)):
        fail("repomix packed files that were not requested; no pack written", extra=extra)


# --- the gate: build accept and review review need this stage's pack, built at HEAD ---


def latest(root: Path, slug: str, stage: str) -> dict | None:
    """The newest manifest for a slug and stage whose pack file still exists."""
    manifests = sorted((packs_dir(root) / slug).glob(f"{stage}-*.json"), key=lambda f: f.stat().st_mtime)
    newest = p.read_json(manifests[-1]) if manifests else None
    return newest if newest and Path(newest["path"]).exists() else None


ACCOUNTED = frozenset({"symlink", "git-ignored"})  # exclusions a committed change can have for good; the gate accepts only these


def require(root: Path, feature: Path, stage: str) -> dict:
    """The gate for a stage in GATED: skipped when packs are off; otherwise refuse without a pack at HEAD."""
    if skipped := off(root):
        return skipped
    if reason := missing_repomix():
        fail(reason, next=INSTALL_CMD)
    cmd = command(stage, feature.name)
    manifest = latest(root, feature.name, stage)
    if not manifest:
        fail(f"no {stage} context pack for {feature.name}; run `{cmd}` first", next=cmd)
    if manifest["head"] != (head := p.head(root)):
        fail(f"the {stage} context pack was built at {manifest['head'][:12]}, not HEAD {head[:12]}; run `{cmd}`", next=cmd)
    if stage == "review":
        changed = review_changes(root)
        if secrets := [{"path": f, "rule": rule} for f in changed if (rule := secret_rule(f))]:
            fail("the branch commits files a secret rule excludes; remove them from history before review", secrets=secrets)
        accounted = set(manifest["files"]) | {e["path"] for e in manifest["excluded"] if e["rule"] in ACCOUNTED}
        if missing := sorted(set(changed) - accounted):
            fail(f"the review context pack does not cover every changed file; run `{cmd}`", missing=missing, next=cmd)
    return {"ok": True, "path": manifest["path"], "head": manifest["head"], "files": len(manifest["files"]), "excluded": manifest["excluded"]}
