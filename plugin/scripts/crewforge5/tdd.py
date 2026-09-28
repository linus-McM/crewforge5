"""TDD evidence (R-T1, R-T2): `build red|green <step>` run `[commands] test` and log the verdict to tdd.jsonl.

red succeeds only when the tests fail, green only when they pass after a red for the same step. Each success
appends `{step, phase, sha, ts, exit}`. `complete(feature)` says whether every Order-of-work step in plan.md has a
red followed by a green; `review run` refuses until it does, and `require` is that refusal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from . import artifacts as a
from . import build
from . import project as p
from .project import fail

LOG = "tdd.jsonl"
REVIEW_RUN = "/crewforge5:review run"
TAIL = 20


def run_tests(root: Path, cmd: str) -> dict:
    proc = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, check=False)  # nosec B602 - the operator-configured [commands] test
    output = (proc.stdout + proc.stderr).strip()
    return {"cmd": cmd, "exit": proc.returncode, "tail": "\n".join(output.splitlines()[-TAIL:])}


def steps(feature: Path) -> list[str]:
    plan = feature / "plan.md"
    return a.steps(plan.read_text()) if plan.exists() else []


def step_id(raw: str | None, known: list[str]) -> str:
    """`3`, `step3` and `step-3` all name Order-of-work step 3; anything else is refused."""
    number = (raw or "").lower().removeprefix("step").strip("-_# ")
    if number not in known:
        fail(f"no Order-of-work step {raw!r} in plan.md (steps: {', '.join(known) or 'none'})", steps=known, next="crewforge5 build red <step number>")
    return number


def pairs(log: list[dict]) -> dict[str, int]:
    """Completed red->green cycles per step: a green closes the most recent open red of its step."""
    done: dict[str, int] = {}
    open_reds: set[str] = set()
    for entry in log:
        step = str(entry.get("step"))
        if entry.get("phase") == "red":
            open_reds.add(step)
        elif entry.get("phase") == "green" and step in open_reds:
            open_reds.discard(step)
            done[step] = done.get(step, 0) + 1
    return done


def cycle(root: Path, slug: str | None, phase: str, raw_step: str | None) -> dict:
    feature = build.implementing(root, slug)
    step = step_id(raw_step, steps(feature))
    cmd = p.config(root)["commands"]["test"]
    if not cmd.strip():
        fail(f"no test command: set [commands] test in {p.CONFIG_NAME}", next=f'add `test = "<command>"` under [commands] in {p.CONFIG_NAME}')
    log = p.read_jsonl(feature / LOG)
    if phase == "green" and not any(e.get("phase") == "red" and str(e.get("step")) == step for e in log):
        fail(f"no red run recorded for step {step}; write its failing test, then `crewforge5 build red {step}`", next=f"crewforge5 build red {step}")
    result = run_tests(root, cmd)
    if phase == "red" and result["exit"] == 0:
        fail(f"tests passed; a red step must fail first ({cmd}). The test is wrong or the behaviour already exists", **result)
    if phase == "green" and result["exit"] != 0:
        fail(f"tests still failing ({cmd}); fix the code, not the tests", **result)
    entry = {"step": step, "phase": phase, "sha": p.head(root), "ts": p.now_iso(), "exit": result["exit"]}
    p.append_jsonl(feature / LOG, entry)
    after = f"implement the smallest change, then `crewforge5 build green {step}`" if phase == "red" else "`crewforge5 build sync`, then commit"
    if phase == "green" and complete(feature)["complete"]:
        after += f"; every step is green: `/simplify`, `crewforge5 build sync`, then {REVIEW_RUN} --slug {feature.name}"
    return {"ok": True, "slug": feature.name, "step": step, "phase": phase, "cycles": pairs([*log, entry]).get(step, 0), "tail": result["tail"], "next": after}


def complete(feature: Path) -> dict:
    """Whether every Order-of-work step has at least one red->green pair in tdd.jsonl."""
    known = steps(feature)
    done = pairs(p.read_jsonl(feature / LOG))
    missing = [s for s in known if not done.get(s)]
    return {"complete": bool(known) and not missing, "steps": known, "missing": missing}


def require(feature: Path) -> dict:
    """Refuse unless the TDD evidence is complete (the `review run` gate, R-T2)."""
    state = complete(feature)
    if not state["complete"]:
        missing = ", ".join(state["missing"]) or "no Order-of-work steps"
        fail(f"tdd.jsonl has no red->green pair for step {missing}", missing=state["missing"], next=f"crewforge5 build red {(state['missing'] or ['<step>'])[0]}")
    return state
