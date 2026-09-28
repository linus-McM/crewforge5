"""Fixtures that drive the crewforge5 verdict CLI in-process and walk a feature through the stages."""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from crewforge5 import artifacts, cli


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    """A fresh git repo with one commit; cwd points at it and checkpoints are off."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@t")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "README.md").write_text("x\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-qm", "init")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CREWFORGE5_CHECKPOINT", "off")  # tests commit nothing unless they take `checkpoint_on`
    monkeypatch.setenv("CREWFORGE5_KNOWLEDGE", "off")  # no Graphify or bundle unless they take `knowledge`
    monkeypatch.setenv("CREWFORGE5_PACKS", "off")  # no Repomix packs or pack gates unless they take `packs`
    monkeypatch.setenv("CREWFORGE5_DOCS", "off")  # no Archify documents or document gates unless they take `docs_tools`
    monkeypatch.delenv("CREWFORGE5_HOME", raising=False)
    return tmp_path


@pytest.fixture
def checkpoint_on(repo: Path, monkeypatch) -> Path:
    """Checkpoints on; list it before any `accepted_*` fixture so their accepts commit."""
    monkeypatch.delenv("CREWFORGE5_CHECKPOINT")
    return repo


@pytest.fixture
def run(repo: Path):
    """Invoke the CLI in-process (never a subprocess of crewforge5.py); return its verdict dict."""

    def _run(*argv: str) -> dict:
        return cli.main([str(a) for a in argv], root=repo)

    return _run


def fill(path: Path, **sections: str) -> None:
    """Replace placeholder bodies under the named sections with real text."""
    text = path.read_text()
    for heading, body in sections.items():
        text = artifacts.set_section(text, heading, body)
    path.write_text(text)


INTENT_BODY = {"Problem": "p", "Proposed outcome": "o", "Affected users and systems": "u", "Constraints": "c", "Open questions": "none"}
SPEC_BODY = {"Requirements": "r", "Design": "d", "Concerns": "none", "Open questions": "none", "Proof": "tests/test_feat.py"}
PLAN_BODY = {
    "Files that change": "- src/feat.py (new)\n- tests/test_feat.py (new)",
    "Order of work": "1. write test_feat, it fails first\n2. implement feat — test: test_feat passes",
    "Risks": "none",
    "Proof": "tests/test_feat.py passes",
}


@pytest.fixture
def accepted_intent(run, repo: Path) -> str:
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    assert run("plan", "accept")["ok"]
    return "feat"


@pytest.fixture
def accepted_spec(run, repo: Path, accepted_intent) -> str:
    run("design", "new")
    fill(repo / "crewforge5/feat/spec.md", **SPEC_BODY)
    assert run("design", "accept")["ok"]
    return "feat"


@pytest.fixture
def accepted_plan(run, repo: Path, accepted_spec) -> str:
    run("build", "new")
    fill(repo / "crewforge5/feat/plan.md", **PLAN_BODY)
    assert run("build", "accept")["ok"]
    return "feat"


@pytest.fixture
def toml_config(repo: Path):
    """Write .crewforge5.toml from {table: {key: value}}; JSON scalars and lists are valid TOML values."""

    def _write(**tables) -> None:
        lines = []
        for table, values in tables.items():
            lines.append(f"[{table}]")
            lines += [f"{k} = {json.dumps(v)}" for k, v in values.items()]
        (repo / ".crewforge5.toml").write_text("\n".join(lines) + "\n")

    return _write


# --- fake external tools (R-K1): graphify, uv, npm, repomix, bandit, node, npx; a test never reaches the real ones ---

FAKE_UV = """#!/bin/sh
echo "uv $*" >> "$(dirname "$0")/calls.log"
if [ "$1 $2 $3" = "tool install graphifyy" ]; then cp "$(dirname "$0")/graphify.hidden" "$(dirname "$0")/graphify"; fi
if [ "$1 $2" = "tool run" ]; then shift 4; exec "$(dirname "$0")/bandit.fake" "$@"; fi
"""
FAKE_GRAPHIFY = """#!/bin/sh
BIN=$(dirname "$0")
echo "graphify $*" >> "$BIN/calls.log"
case "$1 $2" in
  "install --platform") mkdir -p "$CLAUDE_CONFIG_DIR/skills/graphify" && echo skill > "$CLAUDE_CONFIG_DIR/skills/graphify/SKILL.md" ;;
  "update .") mkdir -p graphify-out; sed "s/__COMMIT__/$(git rev-parse HEAD)/" "$BIN/graph.template.json" > graphify-out/graph.json; echo updated ;;
  *) echo "fake graphify: $*" >&2; exit 1 ;;
esac
"""


class FakeTools:
    """Handle on the sandbox: `bin/` holds the fake tools and their call log, `config_dir` is CLAUDE_CONFIG_DIR."""

    def __init__(self, bin_dir: Path, config_dir: Path):
        self.bin, self.config_dir = bin_dir, config_dir

    def calls(self) -> list[str]:
        log = self.bin / "calls.log"
        return log.read_text().splitlines() if log.exists() else []

    @property
    def skill(self) -> Path:
        return self.config_dir / "skills/graphify/SKILL.md"

    @property
    def skill_dir(self) -> Path:
        return self.config_dir / "skills/archify"

    def install(self, name: str, body: str) -> None:
        (self.bin / name).write_text(body.replace("__PYTHON__", sys.executable))
        (self.bin / name).chmod(0o755)

    def uninstall(self, *names: str) -> None:
        for name in names:
            if name == "archify":
                shutil.rmtree(self.skill_dir, ignore_errors=True)
            else:
                (self.bin / name).unlink(missing_ok=True)


@pytest.fixture
def sandbox(repo: Path, tmp_path: Path, monkeypatch) -> FakeTools:
    """A bare PATH (a temp `bin/` plus git and the system dirs), temp HOME and CLAUDE_CONFIG_DIR, all git-excluded."""
    bin_dir, home, config_dir = tmp_path / "bin", tmp_path / "home", tmp_path / "claude"
    bin_dir.mkdir(exist_ok=True)
    home.mkdir(exist_ok=True)
    git_dir = Path(shutil.which("git")).parent
    monkeypatch.setenv("PATH", f"{bin_dir}:{git_dir}:/usr/bin:/bin")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    (repo / ".git/info/exclude").write_text("bin/\nhome/\nclaude/\n")  # the sandbox lives beside the repo files
    return FakeTools(bin_dir, config_dir)


@pytest.fixture
def knowledge(sandbox: FakeTools, monkeypatch) -> FakeTools:
    """Knowledge layer on, with fake `uv` and `graphify` (installed by `uv tool install graphifyy`) in the sandbox."""
    monkeypatch.delenv("CREWFORGE5_KNOWLEDGE")
    sandbox.install("uv", FAKE_UV)
    sandbox.install("graphify.hidden", FAKE_GRAPHIFY)
    (sandbox.bin / "graph.template.json").write_text((Path(__file__).parent / "fixtures/graph.json").read_text())
    return sandbox


FAKE_REPOMIX = """#!__PYTHON__
import html, json, os, pathlib, sys
BIN = pathlib.Path(__file__).parent
args = sys.argv[1:]
if args == ["--version"]:
    print("1.18.0")
    sys.exit(0)
with open(BIN / "calls.log", "a") as log:
    log.write("repomix " + " ".join(args) + "\\n")
paths = [line for line in sys.stdin.read().splitlines() if line.strip()]
with open(BIN / "stdin.log", "a") as log:
    log.write("\\n".join(paths) + "\\n")
out = pathlib.Path(args[args.index("--output") + 1])
config = json.loads(pathlib.Path(args[args.index("--config") + 1]).read_text())
blocks, suspicious, tokens = [], [], 0
for path in paths:
    text = pathlib.Path(path).read_text()
    if "FAKE_SECRET" in text:
        suspicious.append(path)
        continue
    if "FAKE_DROP" in text:
        continue
    blocks.append(f'<file path="{html.escape(path)}">\\n{html.escape(text)}\\n</file>')
    tokens += len(text.encode())
    if "FAKE_EXTRA" in text:
        blocks.append('<file path="unrequested.txt">\\nx\\n</file>')
tokens = tokens // 2 if "--compress" in args else tokens
out.write_text("<files>\\n" + "\\n".join(blocks) + "\\n</files>\\n")
print("Security Check:")
if suspicious and config["security"]["enableSecurityCheck"]:
    print(f"{len(suspicious)} suspicious file(s) detected and excluded from the output:")
    for i, path in enumerate(suspicious, 1):
        print(f"{i}. {path}")
    print("")
else:
    print("No suspicious files detected.")
print(f" Total Tokens: {tokens:,} tokens")
sys.exit(int(os.environ.get("FAKE_REPOMIX_EXIT", "0")))
"""
FAKE_BANDIT = """#!__PYTHON__
import json, pathlib, sys
results = []
for path in [a for a in sys.argv[1:] if a.endswith(".py")]:
    text = pathlib.Path(path).read_text()
    if "FAKE_BANDIT_CRASH" in text:
        sys.exit(2)
    if "FAKE_BANDIT_GARBAGE" in text:
        print("not json")
        sys.exit(0)
    for n, line in enumerate(text.splitlines(), 1):
        if "FAKE_PASSWORD" in line:
            results.append({"filename": "./" + path, "line_number": n, "test_id": "B105", "issue_text": "Possible hardcoded password: " + line})
print(json.dumps({"results": results}))
sys.exit(1 if results else 0)
"""
FAKE_NPM = """#!/bin/sh
BIN=$(dirname "$0")
echo "npm $*" >> "$BIN/calls.log"
if [ "$1 $2 $3" = "i -g repomix" ]; then cp "$BIN/repomix.hidden" "$BIN/repomix"; fi
"""


@pytest.fixture
def packs(knowledge: FakeTools, monkeypatch) -> FakeTools:
    """Context packs on (knowledge layer on too), with fake `repomix`, `npm` and `uv tool run bandit`.
    List any `accepted_*` fixture before this one: its accepts then run while the pack gates are still off."""
    monkeypatch.delenv("CREWFORGE5_PACKS")
    for name, body in {"repomix": FAKE_REPOMIX, "repomix.hidden": FAKE_REPOMIX, "bandit.fake": FAKE_BANDIT, "npm": FAKE_NPM}.items():
        knowledge.install(name, body)
    return knowledge


FAKE_NODE = """#!/bin/sh
BIN=$(dirname "$0")
case "$1" in
  --version) echo "${FAKE_NODE_VERSION:-v20.11.0}"; exit 0 ;;
esac
SCRIPT=$(basename "$1"); shift
echo "node $SCRIPT $* update_check=${ARCHIFY_UPDATE_CHECK_DISABLED:-unset}" >> "$BIN/calls.log"
case "$SCRIPT $1" in
  "archify.mjs deliver")
    IN=$3; OUT=$4
    if grep -q '"fail": true' "$IN"; then echo "composition error: node budget" >&2; exit 1; fi
    printf '<!doctype html><title>fake</title>' > "$OUT"
    SIN=$(sha256sum "$IN" | cut -d' ' -f1); SOUT=$(sha256sum "$OUT" | cut -d' ' -f1)
    echo "delivering $2"
    printf '{\\n  "ok": true,\\n  "specification": {"sha256": "%s"},\\n  "artifact": {"sha256": "%s"},\\n  "validation": {"checksPassed": 9, "checkCount": 9, "errors": 0, "warnings": 0}\\n}\\n' "$SIN" "$SOUT" ;;
  "open-artifact.mjs "*) exit 0 ;;
  *) echo "fake node: $SCRIPT $*" >&2; exit 1 ;;
esac
"""
FAKE_NPX = """#!/bin/sh
echo "npx $*" >> "$(dirname "$0")/calls.log"
mkdir -p "$CLAUDE_CONFIG_DIR/skills/archify/bin"; echo "// fake" > "$CLAUDE_CONFIG_DIR/skills/archify/bin/archify.mjs"
"""


def install_fake_archify(config_dir: Path) -> None:
    skill = config_dir / "skills/archify"
    (skill / "bin").mkdir(parents=True, exist_ok=True)
    (skill / "bin/archify.mjs").write_text("// fake\n")
    (skill / "bin/open-artifact.mjs").write_text("// fake\n")
    (skill / "skill-release.json").write_text('{"version": "2.17.0"}\n')


def sha256(*chunks: bytes) -> str:
    return hashlib.sha256(b"".join(chunks)).hexdigest()


@pytest.fixture
def docs_tools(sandbox: FakeTools, monkeypatch) -> FakeTools:
    """Stage documents on, with fake `node` and `npx` in the sandbox and a fake Archify skill installed.
    List any `accepted_*` fixture before this one, or its accepts are refused for want of a document."""
    monkeypatch.delenv("CREWFORGE5_DOCS")
    monkeypatch.delenv("CI", raising=False)
    sandbox.install("node", FAKE_NODE)
    sandbox.install("npx", FAKE_NPX)
    install_fake_archify(sandbox.config_dir)
    return sandbox


SOURCES = {"src__app__core.py": "def run(): pass\n", "src__app__util.py": "u = 1\n", "src__web__api.py": "a = 1\n", "src__web__views.py": "v = 1\n", "docs__guide.md": "g\n"}


def commit_files(repo: Path, message: str = "x", **files: str) -> str:
    """Write `files` (keys use __ for /), commit everything, return HEAD."""
    for key, text in files.items():
        path = repo / key.replace("__", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", message, "--allow-empty")
    return git(repo, "rev-parse", "HEAD")


def regraph(repo: Path, **files: str) -> None:
    """Commit `files`, then rebuild graph.json at the new HEAD, as `knowledge refresh` would."""
    commit_files(repo, **files)
    subprocess.run(["graphify", "update", "."], cwd=repo, check=True, capture_output=True)
