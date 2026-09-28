"""Continuous evals (`review evals`): run each `evals/*.json` prompt through `claude -p`, then its deterministic checks.

An eval is `{prompt, allowed_tools?, checks?}`; it passes when the agent exits 0 and every check command exits 0.
The suite passes at `[evals] threshold` (default 1.0). CREWFORGE5_CLAUDE_BIN names the binary (tests stub it).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from . import project as p
from . import tdd
from .project import fail

REPORT = "evals-report.json"


def run_eval(root: Path, path: Path) -> dict:
    try:
        spec = json.loads(path.read_text())
    except json.JSONDecodeError as err:
        return fail(f"{p.rel(root, path)} is not valid JSON ({err.msg} at line {err.lineno})", path=str(path))
    if not isinstance(spec, dict) or not str(spec.get("prompt", "")).strip():
        fail(f"{p.rel(root, path)} needs a `prompt`", path=str(path), next="write {prompt, allowed_tools, checks} into it")
    cmd = [os.environ.get("CREWFORGE5_CLAUDE_BIN", "claude"), "-p", spec["prompt"], "--output-format", "json"]
    if spec.get("allowed_tools"):
        cmd += ["--allowedTools", ",".join(spec["allowed_tools"])]
    try:
        agent = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
        agent_exit = agent.returncode
    except FileNotFoundError:
        agent_exit = 127
    checks = [tdd.run_tests(root, check) for check in spec.get("checks", [])]
    return {"name": path.stem, "passed": agent_exit == 0 and all(c["exit"] == 0 for c in checks), "agent_exit": agent_exit, "checks": checks}


def run(root: Path) -> dict:
    suite = sorted((root / "evals").glob("*.json"))
    if not suite:
        fail("no evals/*.json found; write one per real task with its prompt and checks", next="add evals/<task>.json")
    results = [run_eval(root, path) for path in suite]
    rate = sum(r["passed"] for r in results) / len(results)
    threshold = float(p.config(root)["evals"]["threshold"])
    report = {"pass_rate": rate, "threshold": threshold, "results": results, "ts": p.now_iso()}
    home = p.home(root)
    home.mkdir(parents=True, exist_ok=True)
    p.write_json(home / REPORT, report)
    if rate < threshold:
        fail(f"pass rate {rate:.2f} below threshold {threshold}", **report, next="fix the agent setup the failing evals exercise, then `crewforge5 review evals`")
    return {"ok": True, **report, "path": str(home / REPORT), "next": "nothing to do: the eval suite passes"}
