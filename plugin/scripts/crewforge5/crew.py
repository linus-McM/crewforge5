"""The crew factory as a command (R-S5): `crew survey|validate|status`, and the crew gate `build accept` applies.

The crew itself is agent work (`stack-surveyor` writes `.claude/crews/<lang>.profile.md`, `crew-factory` the agents and
`.claude/crews/<lang>.json`); this module only reads and grades it. `survey` detects the language through team-sprint's
`detect_language.sh` (or `[project] language`); `validate` runs `crew_check.sh check` and re-grades every generated agent
through the agent validator; `status` reports each manifest's `validation` grades. With `[build] require_crew = true`,
`build accept` refuses until the plan's language has a crew whose grades pass, and `next` is `/crewforge5:crew forge <lang>`.
"""

from __future__ import annotations

from pathlib import Path

from . import init
from . import project as p
from .project import fail

CREWS = ".claude/crews"
AGENTS = ".claude/agents"
SCRIPTS = "skills/team-sprint/scripts"
PASSING = ("A",)  # crew-factory ships a generated agent only at grade A
REQUIRED = ("language", "stack_profile", "commands", "crew", "validation", "generated", "reused")


def command(action: str, lang: str | None = None) -> str:
    return f"/crewforge5:crew {action}" + (f" {lang}" if lang else "")


def detect(root: Path) -> dict:
    """`[project] language`, else detect_language.sh: {language, status, candidates}."""
    if lang := str(p.config(root)["project"].get("language", "")).strip():
        return {"language": lang, "status": "CONFIGURED", "candidates": [lang]}
    out = p.kv(p.script(root, f"{SCRIPTS}/detect_language.sh", str(root))["stdout"])
    candidates = [c for c in out.get("CANDIDATES", out.get("LANG", "")).split(",") if c]
    return {"language": out.get("LANG") if out.get("STATUS") == "OK" else None, "status": out.get("STATUS", "UNKNOWN"), "candidates": candidates}


def language(root: Path, arg: str | None) -> str:
    if arg:
        return arg
    found = detect(root)
    if not found["language"]:
        fail(
            f"cannot tell the project language ({found['status']}{': ' + ', '.join(found['candidates']) if found['candidates'] else ''})",
            candidates=found["candidates"],
            next=f"name it: set [project] language in {p.CONFIG_NAME}, or pass <lang>",
        )
    return found["language"]


def manifest(root: Path, lang: str) -> dict | None:
    data = p.read_json(root / CREWS / f"{lang}.json")
    return data if isinstance(data, dict) else None


def report(root: Path, lang: str) -> dict:
    """One crew's grades and what keeps it from passing: every generated agent graded, every grade passing."""
    data = manifest(root, lang)
    if data is None:
        return {"language": lang, "path": f"{CREWS}/{lang}.json", "exists": False, "grades": {}, "passing": False, "problems": ["no manifest"]}
    problems = [f"manifest missing `{key}`" for key in REQUIRED if key not in data]
    grades = data.get("validation") if isinstance(data.get("validation"), dict) else {}
    generated = data.get("generated") if isinstance(data.get("generated"), list) else []
    if not grades:
        problems.append("no validation grades recorded")
    problems += [f"{name} has no validation grade" for name in generated if name not in grades]
    problems += [f"{name} graded {grade}" for name, grade in grades.items() if str(grade).upper() not in PASSING]
    return {
        "language": lang,
        "path": f"{CREWS}/{lang}.json",
        "exists": True,
        "roles": data.get("crew", {}),
        "grades": grades,
        "passing": not problems,
        "problems": problems,
    }


def status(root: Path, lang: str | None) -> dict:
    langs = [lang] if lang else sorted(f.stem for f in (root / CREWS).glob("*.json"))
    crews = [report(root, name) for name in langs]
    if not crews:
        return {"ok": True, "crews": [], "next": command("survey")}
    failing = [c["language"] for c in crews if not c["passing"]]
    return {"ok": True, "crews": crews, "next": command("forge", failing[0]) if failing else "nothing to do: every crew passes"}


def survey(root: Path) -> dict:
    found = detect(root)
    lang = found["language"]
    profile = root / CREWS / f"{lang}.profile.md" if lang else None
    if not lang:
        after = f"pick the primary language (candidates: {', '.join(found['candidates']) or 'none'}), set [project] language, then {command('survey')}"
    elif not profile.exists():
        after = f"spawn the crewforge5:stack-surveyor agent for {lang}; it writes {CREWS}/{lang}.profile.md"
    else:
        after = "nothing to do: every crew passes" if report(root, lang)["passing"] else command("forge", lang)
    return {"ok": True, **found, "profile": str(profile.relative_to(root)) if profile and profile.exists() else None, "next": after}


def validate(root: Path, lang_arg: str | None) -> dict:
    """crew_check.sh's structural verdict, then a fresh grade of each generated agent, then the recorded grades."""
    lang = language(root, lang_arg)
    checked = p.kv(p.script(root, f"{SCRIPTS}/crew_check.sh", "check", lang, "--project-dir", str(root))["stdout"])
    problems = [] if checked.get("STATUS") == "CACHED" else [f"crew_check: {checked.get('STATUS', 'no verdict')} {checked.get('REASON', '')}".strip()]
    graded = {}
    for name in (manifest(root, lang) or {}).get("generated", []):
        path = root / AGENTS / f"{name}.md"
        if path.is_file():
            graded[name] = init.grade(root, "agent", path)["grade"]
            if graded[name] not in PASSING:
                problems.append(f"{name} now grades {graded[name]}")
    crew = report(root, lang)
    problems += [f for f in crew["problems"] if f not in problems]
    if problems:
        fail(f"the {lang} crew does not pass: {'; '.join(problems)}", language=lang, problems=problems, measured=graded, next=command("forge", lang))
    return {**crew, "ok": True, "measured": graded, "worktree_agents": checked.get("WORKTREE_AGENTS"), "next": "nothing to do: the crew passes"}


def require(root: Path) -> None:
    """The `build accept` gate, when `[build] require_crew` is on."""
    if not p.config(root)["build"].get("require_crew"):
        return
    lang = language(root, None)
    if not (crew := report(root, lang))["passing"]:
        fail(f"no {lang} crew with passing validation grades ({'; '.join(crew['problems'])}); [build] require_crew is on", language=lang, next=command("forge", lang))
