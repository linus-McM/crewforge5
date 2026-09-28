"""Config hygiene (R-S4): `init new|check|accept|status` over `<home>/init-<date>/audit.md`.

`new` measures the config root through the scripts the legacy init flow already ships (token-slim's `baseline.py`,
the skill and agent validators, `grade.sh`) plus the context-hygiene inventory (CLAUDE.md, rules, hooks, MCP servers),
writes the before-picture to `measure.json` and renders `audit.md` with its Baseline filled. `check` validates the
audit; `accept` (only after a human approves the edits) runs `retention_gate.sh` over every changed instruction file,
re-measures, refuses a rise in validator failures, records the Result and is a stage boundary: `cli.main` commits
`init(<slug>): accept — audit.md`.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from . import artifacts as a
from . import project as p
from .project import fail

AUDIT = "audit.md"
MEASURE = "measure.json"
PREFIX = "init-"
BASELINE = "skills/token-slim/scripts/baseline.py"
VALIDATORS = {"skill": "skills/skill-validator/scripts/validate_structure.sh", "agent": "skills/agent-validator/scripts/validate_agent.sh"}
GRADE = "skills/skill-validator/scripts/grade.sh"
RETENTION = "scripts/retention_gate.sh"
FINDING = re.compile(r"^\s*[-*]\s+(.*)$")
TAG = re.compile(r"^(?:\*\*)?(Important|Nit)(?:\*\*)?:\s*\S")
DESCRIPTION = re.compile(r"^description:[ \t]*(.*)$", re.MULTILINE)


def command(action: str, slug: str | None = None) -> str:
    return f"/crewforge5:init {action}" + (f" --slug {slug}" if slug else "")


# --- measurement ------------------------------------------------------------


def target(root: Path, arg: str | None) -> Path:
    """The config root under audit: the argument, else `[init] target`, else `.claude/` when present, else the project."""
    name = arg or p.config(root)["init"]["target"] or (".claude" if (root / ".claude").is_dir() else ".")
    path = Path(name).expanduser()
    path = path if path.is_absolute() else root / path
    if not path.is_dir():
        fail(f"config root {name!r} is not a directory", next=f"{command('new')} <config root>, or set [init] target in {p.CONFIG_NAME}")
    return path


def shown(root: Path, path: Path) -> str:
    """A path relative to the project when inside it, else as given."""
    resolved = path.resolve()
    return str(resolved.relative_to(root.resolve())) if resolved.is_relative_to(root.resolve()) else str(path)


def grade(root: Path, kind: str, path: Path) -> dict:
    """One component through its structural validator, graded by grade.sh (A = 0 FAIL, at most 2 WARN)."""
    out = p.script(root, VALIDATORS[kind], str(path))
    raw = [line.strip().rstrip(",") for line in out["stdout"].splitlines() if re.search(r'"status":"(FAIL|WARN)"', line)]
    with tempfile.NamedTemporaryFile("w", suffix=".findings", delete=False) as fh:
        fh.write("\n".join(raw) + "\n")
    try:
        graded = p.kv(p.script(root, GRADE, fh.name)["stdout"])
    finally:
        Path(fh.name).unlink()
    counts = {k: int(graded.get(k, "0") or 0) for k in ("fails", "warns")}
    return {"kind": kind, "name": path.stem if kind == "agent" else path.name, "grade": graded.get("grade", "F"), **counts, "findings": [readable(line) for line in raw]}


def readable(line: str) -> str:
    """`{"status":"WARN","check":"c","detail":"d"}` -> `WARN c: d`; anything else as is."""
    try:
        item = json.loads(line)
        return f"{item['status']} {item['check']}: {item['detail']}"
    except (json.JSONDecodeError, KeyError, TypeError):
        return line


def described(path: Path) -> int:
    found = DESCRIPTION.search(path.read_text(errors="replace").split("\n---", 1)[0])
    return len(found.group(1).strip().strip("\"'")) if found else 0


def files(root: Path, config_root: Path) -> dict[str, list[Path]]:
    """The always-loaded instruction files and the settings that carry hooks, deduplicated across the two roots."""
    roots = list(dict.fromkeys([root, root / ".claude", config_root]))
    pick = lambda names: list(dict.fromkeys(r / n for r in roots for n in names if (r / n).is_file()))  # noqa: E731
    rules = list(dict.fromkeys(f for r in roots for f in sorted((r / "rules").glob("*.md"))))
    return {"claude_md": pick(["CLAUDE.md", "CLAUDE.local.md"]), "rules": rules, "settings": pick(["settings.json", "settings.local.json"])}


def hooks_in(path: Path) -> int:
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    groups = data.get("hooks", {}) if isinstance(data, dict) else {}
    return sum(len(g.get("hooks", [])) for event in groups.values() if isinstance(event, list) for g in event if isinstance(g, dict))


def mcp_servers(root: Path) -> list[str]:
    try:
        data = json.loads((root / ".mcp.json").read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return sorted(data.get("mcpServers", {})) if isinstance(data, dict) else []


def measure(root: Path, config_root: Path) -> dict:
    """The before- or after-picture of one config root."""
    skills_dir, agents_dir = config_root / "skills", config_root / "agents"
    skills = {}
    if skills_dir.is_dir():
        out = p.script(root, BASELINE, "--skills-dir", str(skills_dir), "--report")
        try:
            skills = json.loads(out["stdout"] or "{}")
        except json.JSONDecodeError:
            fail(f"token-slim baseline.py did not print JSON ({out['stderr'].strip()[-200:]})", next="fix the skills directory, then re-run")
    agents = {f.stem: {"desc_chars": described(f)} for f in sorted(agents_dir.glob("*.md"))} if agents_dir.is_dir() else {}
    components = [grade(root, "agent", f) for f in sorted(agents_dir.glob("*.md"))] if agents_dir.is_dir() else []
    components += [grade(root, "skill", d) for d in sorted(skills_dir.iterdir()) if (d / "SKILL.md").is_file()] if skills_dir.is_dir() else []
    found = files(root, config_root)
    context = {
        "claude_md": [{"path": shown(root, f), "lines": len(f.read_text().splitlines()), "chars": len(f.read_text())} for f in found["claude_md"]],
        "rules": [{"path": shown(root, f), "chars": len(f.read_text())} for f in found["rules"]],
        "hooks": sum(hooks_in(f) for f in found["settings"]),
        "mcp_servers": mcp_servers(root),
    }
    desc = sum(int(s.get("desc_chars", 0)) for s in skills.values()) + sum(a_["desc_chars"] for a_ in agents.values())
    instructions = sum(f["chars"] for f in context["claude_md"] + context["rules"])
    totals = {
        "desc_chars": desc,
        "instruction_chars": instructions,
        "always_loaded_tokens": round((desc + instructions) / 4),
        "fails": sum(c["fails"] for c in components),
        "warns": sum(c["warns"] for c in components),
        "below_a": [f"{c['kind']}:{c['name']}={c['grade']}" for c in components if c["grade"] != "A"],
    }
    skills = {name: {"desc_chars": s.get("desc_chars", 0), "body_chars": s.get("body_chars", 0)} for name, s in skills.items()}
    return {"target": shown(root, config_root), "skills": skills, "agents": agents, "components": components, "context": context, "totals": totals}


def baseline_md(m: dict) -> str:
    """The Baseline section: generated, so an audit always starts from numbers, not impressions."""
    t, c = m["totals"], m["context"]
    lines = [
        f"Config root: `{m['target']}`. Always-loaded ~{t['always_loaded_tokens']} tok (descriptions {t['desc_chars']} chars, CLAUDE.md and rules {t['instruction_chars']} chars).",
        f"- Skills: {len(m['skills'])}; agents: {len(m['agents'])}; validator FAIL {t['fails']}, WARN {t['warns']}; below grade A: {', '.join(t['below_a']) or 'none'}",
        "- CLAUDE.md: " + (", ".join(f"`{f['path']}` {f['lines']} lines" for f in c["claude_md"]) or "none"),
        f"- Rules: {len(c['rules'])} files, {sum(f['chars'] for f in c['rules'])} chars; hooks: {c['hooks']}; MCP servers: {', '.join(c['mcp_servers']) or 'none'}",
    ]
    lines += [f"- {comp['kind']} `{comp['name']}` {comp['grade']}: {finding}" for comp in m["components"] for finding in comp["findings"]]
    return "\n".join(lines)


# --- the lifecycle ----------------------------------------------------------


def audits(root: Path) -> list[Path]:
    base = p.home(root)
    return sorted(d for d in base.glob(f"{PREFIX}*") if d.is_dir()) if base.is_dir() else []


def folder(root: Path, slug: str | None) -> Path:
    """The named audit folder, or the most recent `init-*` one."""
    if slug:
        path = p.home(root) / slug
        if (path / AUDIT).exists():
            return path
        return fail(f"no {AUDIT} under {p.rel(root, path)}/", next=command("status"))
    if found := [d for d in audits(root) if (d / AUDIT).exists()]:
        return found[-1]
    return fail("no config audit found", next=command("new"))


def new(root: Path, arg: str | None, slug: str | None) -> dict:
    config_root = target(root, arg)
    slug = slug or f"{PREFIX}{p.today()}"
    path = p.home(root) / slug / AUDIT
    if path.exists():
        fail(f"{p.rel(root, path)} already exists", slug=slug, next=command("check", slug))
    before = measure(root, config_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    p.write_json(path.parent / MEASURE, {"before": before})
    fields = {"title": before["target"], "author": p.author(root), "date": p.today(), "baseline": baseline_md(before)}
    path.write_text(a.render(p.TEMPLATES / AUDIT, **fields))
    created = p.ensure_config(root)
    after = f"run crewforge5:config-audit (or the inline passes), fill Findings, Proposed edits and Retention, then {command('check', slug)}"
    return {"ok": True, "slug": slug, "path": str(path), "target": before["target"], "totals": before["totals"], "config_created": created, "next": after}


def problems(text: str) -> list[str]:
    found = a.validate(text, a.REQUIRED[AUDIT])
    for line in a.sections(text).get("Findings", "").splitlines():
        if (bullet := FINDING.match(line)) and bullet.group(1).strip().lower().rstrip(".") != "none" and not TAG.match(bullet.group(1).strip()):
            found.append(f"Findings: a finding must start `Important:` or `Nit:` ({bullet.group(1).strip()[:60]})")
    return found


def check(root: Path, slug: str | None) -> dict:
    audit = folder(root, slug)
    path = audit / AUDIT
    if not (audit / MEASURE).exists():
        fail(f"{MEASURE} missing: the before-picture is gone; start over with {command('new')}", slug=audit.name, next=command("new"))
    if found := problems(path.read_text()):
        fail("; ".join(found), slug=audit.name, path=str(path), problems=found, next=f"fix {AUDIT}, then {command('check', audit.name)}")
    return {"ok": True, "slug": audit.name, "path": str(path), "problems": [], "next": command("accept", audit.name)}


def changed_instructions(root: Path, config_root: Path) -> list[str]:
    """Tracked markdown under the config root, and CLAUDE.md files, modified since HEAD (the edits accept applies)."""
    names = p.git(root, "diff", "--name-only", "--relative", "--diff-filter=M", "HEAD").splitlines()
    inside = shown(root, config_root)
    return [n for n in names if n.endswith(".md") and (Path(n).name.startswith("CLAUDE") or inside == "." or n.startswith(inside.rstrip("/") + "/"))]


def retention(root: Path, changed: list[str]) -> list[str]:
    """retention_gate.sh over each changed file against its HEAD version; one entry per lost line."""
    losses = []
    for name in changed:
        with tempfile.NamedTemporaryFile("w", suffix=".orig", delete=False) as fh:
            fh.write(p.git(root, "show", f"HEAD:{name}") + "\n")
        try:
            out = p.script(root, RETENTION, fh.name, str(root / name))
        finally:
            Path(fh.name).unlink()
        if out["exit"] != 0:
            lost = [line.strip() for line in (out["stdout"] + out["stderr"]).splitlines() if line.strip()]
            lost = [line for line in lost if "FAIL" in line] or lost
            losses += [f"{name}: {line}" for line in lost] or [f"{name}: retention gate failed"]
    return losses


def result_md(before: dict, after: dict) -> str:
    b, t = before["totals"], after["totals"]
    return "\n".join(
        [
            f"- DESC_CHARS_BEFORE={b['desc_chars']} DESC_CHARS_AFTER={t['desc_chars']} DESC_CHARS_DELTA={b['desc_chars'] - t['desc_chars']}",
            f"- INSTRUCTION_CHARS_BEFORE={b['instruction_chars']} INSTRUCTION_CHARS_AFTER={t['instruction_chars']}",
            f"- Always-loaded ~{b['always_loaded_tokens']} tok -> ~{t['always_loaded_tokens']} tok",
            f"- Validator FAIL {b['fails']} -> {t['fails']}, WARN {b['warns']} -> {t['warns']}; below grade A: {', '.join(t['below_a']) or 'none'}",
        ]
    )


def accept(root: Path, slug: str | None) -> dict:
    """Only a human accepts: the command asks (AskUserQuestion) and applies the approved edits before it calls this."""
    verdict = check(root, slug)
    path = Path(verdict["path"])
    audit, name = path.parent, path.parent.name
    before = p.read_json(audit / MEASURE, {}).get("before") or fail(f"{MEASURE} has no before-picture", slug=name, next=command("new"))
    config_root = target(root, before["target"])
    changed = changed_instructions(root, config_root)
    if losses := retention(root, changed):
        fail("retention breach: an applied edit lost a line that must survive", slug=name, losses=losses, next=f"restore the lost lines, then {command('accept', name)}")
    after = measure(root, config_root)
    if after["totals"]["fails"] > before["totals"]["fails"]:
        fail(
            f"validator failures rose from {before['totals']['fails']} to {after['totals']['fails']}; an applied edit broke a component",
            slug=name,
            below_a=after["totals"]["below_a"],
            next=f"fix or revert the edit, then {command('accept', name)}",
        )
    text = a.set_meta(path.read_text(), "Status", "accepted")
    body = result_md(before, after)
    text = a.set_section(text, "Result", body) if "Result" in a.sections(text) else text.rstrip() + f"\n\n## Result\n{body}\n"
    path.write_text(text)
    p.write_json(audit / MEASURE, {"before": before, "after": after})
    edits = set(changed)
    if before["target"] != "." and not Path(before["target"]).is_absolute():  # a config root inside the project: its new files too
        edits |= set(p.changed_files(root, before["target"]))
    config_edits = sorted(edits)
    after_step = f"commit the applied config edits: git commit -m 'chore(config): apply {name}' -- {' '.join(config_edits)}" if config_edits else "nothing to do: the audit is accepted"
    delta = before["totals"]["desc_chars"] - after["totals"]["desc_chars"]
    return {"ok": True, "slug": name, "path": str(path), "status": "accepted", "desc_chars_delta": delta, "totals": after["totals"], "changed": config_edits, "next": after_step}


def status(root: Path) -> dict:
    listed = []
    for audit in audits(root):
        path = audit / AUDIT
        state = (a.status(path.read_text()) or "draft") if path.exists() else "missing"
        nxt = {"missing": command("new"), "draft": command("check", audit.name)}.get(state, "nothing to do: accepted")
        listed.append({"slug": audit.name, "audit": state, "next": nxt})
    after = listed[-1]["next"] if listed and listed[-1]["audit"] != "accepted" else command("new")
    return {"ok": True, "audits": listed, "next": after}
