"""R-K2, R-K3, C5: graph-selected Repomix context packs — seeds, expansion, secret exclusion, the pack and its gates."""

import json
import subprocess
from pathlib import Path

import pytest

from conftest import INTENT_BODY, PLAN_BODY, SOURCES, commit_files, fill, regraph
from crewforge5 import project as p

GRAPH = Path(__file__).parent / "fixtures/graph.json"


def test_pack_config_defaults(repo: Path):
    conf = p.config(repo)["packs"]
    assert conf == {"enabled": True, "max_tokens": 0, "hops": 1, "base": "main"}


def test_expand_is_one_hop_over_calls_plus_community():
    from crewforge5 import packs

    got = packs.expand(json.loads(GRAPH.read_text()), ["src/web/api.py"], 1)
    assert got == {"src/web/api.py": "seed", "src/app/core.py": "callee", "src/web/views.py": "callee"}


def feature_dir(repo: Path, **artifacts_: str) -> Path:
    feature = repo / "crewforge5/feat"
    feature.mkdir(parents=True, exist_ok=True)
    for name, text in artifacts_.items():
        (feature / name.replace("_", ".")).write_text(text)
    return feature


def test_seeds_per_stage(repo: Path):
    from crewforge5 import packs

    commit_files(repo, **SOURCES)
    feature = feature_dir(
        repo,
        intent_md="# Intent: Feat\n\n## Affected users and systems\n- `src/app/core.py:12`, the `src/web/` package and `docs/*.md`\n",
        spec_md="# Spec: Feat\n\n## Design\nReuses `src/app/util.py`.\n",
        plan_md="# Plan: Feat\n\n## Files that change\n- src/app/core.py\n- tests/test_new.py (new)\n",
    )
    assert packs.seeds(repo, feature, "plan") == (["docs/guide.md", "src/app/core.py", "src/web/api.py", "src/web/views.py"], [])
    assert "src/app/util.py" in packs.seeds(repo, feature, "design")[0]
    assert packs.seeds(repo, feature, "build") == (["src/app/core.py"], ["tests/test_new.py"])
    subprocess.run(["git", "checkout", "-qb", "feat"], cwd=repo, check=True)
    commit_files(repo, **{"src__app__core.py": "def run(): return 1\n", "crewforge5__feat__review.md": "r\n"})
    assert packs.seeds(repo, feature, "review") == (["src/app/core.py"], [])  # the feature's own artifacts never seed


def test_secret_exclusion_applies_after_expansion(repo: Path):
    """C5: the frozen exclude list, untracked, symlinked and git-ignored files never reach Repomix; verdicts name rules."""
    from crewforge5 import packs

    secrets = {
        ".env.local": "K=1\n",
        "keys__id_rsa": "k\n",
        "x.pem": "k\n",
        "tls__server.crt": "c\n",
        ".npmrc": "t\n",
        ".netrc": "n\n",
        ".pypirc": "p\n",
        "my_credentials.json": "{}\n",
        ".claude__settings.local.json": "{}\n",
    }
    commit_files(repo, **SOURCES, **secrets, **{".gitignore": "ignored.txt\ngraphify-out/\n"})
    for name in ("ignored.txt", "graphify-out/x"):
        (repo / name).parent.mkdir(exist_ok=True)
        (repo / name).write_text("i\n")
        subprocess.run(["git", "add", "-f", name], cwd=repo, check=True)
    (repo / "link.py").symlink_to("src/app/core.py")
    commit_files(repo)
    (repo / "new.py").write_text("n\n")
    names = ["src/app/core.py", "new.py", "link.py", "ignored.txt", "graphify-out/x", *[k.replace("__", "/") for k in secrets]]
    admitted, excluded = packs.admit(repo, names)
    assert admitted == ["src/app/core.py"]
    rules = {e["path"]: e["rule"] for e in excluded}
    assert set(rules) == set(names) - {"src/app/core.py"}
    assert rules["new.py"] == "untracked" and rules["link.py"] == "symlink" and rules["ignored.txt"] == "git-ignored"
    assert rules[".env.local"] == ".env*" and rules["keys/id_rsa"] == "id_rsa*" and rules["graphify-out/x"] == "graphify-out/**"
    assert rules[".claude/settings.local.json"] == ".claude/settings.local.json" and rules["my_credentials.json"] == "*credentials*"
    assert rules[".npmrc"] == ".npmrc" and rules[".netrc"] == ".netrc" and rules[".pypirc"] == ".pypirc" and rules["tls/server.crt"] == "*.crt"
    assert packs.secret_rule("keys/SERVER.PEM") == "*.pem" and packs.secret_rule(".ENV") == ".env*"


def test_exclude_list_is_frozen(repo: Path):
    from crewforge5 import packs

    assert isinstance(packs.EXCLUDE, tuple) and all(isinstance(rule, str) for rule in packs.EXCLUDE)
    config = p.config(repo)
    assert not [key for table in ("knowledge", "packs") for key in config[table] if "exclude" in key]
    assert json.loads(packs.CONFIG.read_text())["security"]["enableSecurityCheck"] is True


INTENT = "# Intent: Feat\nAuthor: t. Status: draft. Risk: low.\n\n## Affected users and systems\n- `src/web/api.py`\n"


def ready(run, repo: Path, toml_config) -> Path:
    """Sources and a feature committed, the knowledge layer bootstrapped: graph.json is fresh at HEAD."""
    toml_config(knowledge={"auto_install": True})
    commit_files(repo, **SOURCES, **{"crewforge5__feat__intent.md": INTENT})
    assert run("knowledge", "bootstrap")["ok"]
    commit_files(repo, "bootstrap output")  # .graphifyignore, the config and the bundle: all exempt from freshness
    return repo / "crewforge5/feat"


def pack(run, stage: str = "plan", *extra: str) -> dict:
    return run("knowledge", "pack", stage, "--slug", "feat", *extra)


def test_pack_writes_xml_and_manifest_never_committed(run, repo: Path, packs, toml_config):
    ready(run, repo, toml_config)
    verdict = pack(run)
    assert verdict["ok"] and verdict["reused"] is False and verdict["stage"] == "knowledge", verdict
    manifest = json.loads(Path(verdict["manifest"]).read_text())
    assert verdict["path"] == str(repo / f"graphify-out/packs/feat/plan-{manifest['key'][:12]}.xml") and Path(verdict["path"]).exists()
    assert manifest["head"] == p.head(repo) and manifest["repomix_version"] == "1.18.0"
    assert set(verdict["files"]) == {"src/web/api.py", "src/app/core.py", "src/web/views.py"} and verdict["seeds"] == ["src/web/api.py"]
    assert "args.pack" in verdict["next"]
    call = next(c for c in packs.calls() if c.startswith("repomix "))
    assert f"--stdin --config {p.TEMPLATES / 'knowledge/repomix.config.json'} --style xml" in call and "--no-security-check" not in call
    assert (repo / "graphify-out/packs/.gitignore").read_text() == "*\n"
    assert "graphify-out/packs" not in p.git(repo, "status", "--porcelain", "--untracked-files=all")
    again = pack(run)
    assert again["reused"] is True and again["path"] == verdict["path"]


def test_pack_refuses_unknown_stage_stale_graph_and_dirty_files(run, repo: Path, packs, toml_config):
    ready(run, repo, toml_config)
    assert pack(run, "deploy")["ok"] is False
    (repo / "src/web/api.py").write_text("a = 3\n")
    dirty = pack(run)
    assert dirty["ok"] is False and dirty["dirty"] == ["src/web/api.py"]
    commit_files(repo, **{"src__app__util.py": "u = 2\n"})
    stale = pack(run)
    assert stale["ok"] is False and "src/app/util.py" in stale["stale"] and stale["next"] == "crewforge5 knowledge refresh"


@pytest.mark.parametrize(("marker", "named"), [("FAKE_SECRET", "src/web/api.py"), ("FAKE_DROP", "src/web/api.py"), ("FAKE_EXTRA", "unrequested.txt"), ("exit", "exited 3")])
def test_output_scanner_refuses_and_never_echoes_content(run, repo: Path, packs, toml_config, monkeypatch, marker, named):
    ready(run, repo, toml_config)
    if marker == "exit":
        monkeypatch.setenv("FAKE_REPOMIX_EXIT", "3")
    else:
        regraph(repo, **{"src__web__api.py": f"token = '{marker} value'\n"})
    verdict = pack(run)
    assert not verdict["ok"] and "value" not in json.dumps(verdict) and named in json.dumps(verdict)
    folder = repo / "graphify-out/packs/feat"
    assert not folder.exists() or list(folder.iterdir()) == []


def test_bandit_fails_closed(run, repo: Path, packs, toml_config):
    ready(run, repo, toml_config)
    regraph(repo, **{"src__web__api.py": "a = 1\npw = 'FAKE_PASSWORD hunter2'\n"})
    verdict = pack(run)
    assert not verdict["ok"] and verdict["findings"] == ["src/web/api.py:2 B105"] and "hunter2" not in json.dumps(verdict)
    assert not any(c.startswith("repomix ") for c in packs.calls())
    for marker in ("FAKE_BANDIT_CRASH", "FAKE_BANDIT_GARBAGE"):
        regraph(repo, **{"src__web__api.py": f"# {marker}\n"})
        out = pack(run)
        assert not out["ok"] and "bandit" in out["reason"] and "fails closed" in out["reason"]


def test_budget_ladder(run, repo: Path, packs, toml_config):
    ready(run, repo, toml_config)
    assert [s["rung"] for s in pack(run)["steps"]] == ["full"]
    seeds_only = pack(run, "plan", "--max-tokens", "5")
    assert [s["rung"] for s in seeds_only["steps"]] == ["full", "compress", "seeds"] and list(seeds_only["files"]) == ["src/web/api.py"]
    assert seeds_only["over_budget"] is False


def test_missing_repomix_skips_advisory_and_refuses_gated(run, repo: Path, packs, toml_config):
    ready(run, repo, toml_config)
    packs.uninstall("repomix")
    advisory = pack(run, "design")
    assert advisory["ok"] and "npm i -g repomix" in advisory["skipped"]
    gated = pack(run, "build")
    assert not gated["ok"] and "npm i -g repomix" in gated["reason"]


def test_packs_off_is_skipped(run, repo: Path, packs, toml_config, monkeypatch):
    ready(run, repo, toml_config)
    monkeypatch.setenv("CREWFORGE5_PACKS", "off")
    assert pack(run) == {"ok": True, "skipped": "packs disabled", "stage": "knowledge"}
    monkeypatch.setenv("CREWFORGE5_KNOWLEDGE", "off")
    assert pack(run) == {"ok": True, "skipped": "knowledge disabled", "stage": "knowledge"}


def accepted_spec_with_graph(run, repo: Path, toml_config) -> None:
    """A feature walked to an accepted spec with the pack gates off, then committed and graphed."""
    toml_config(knowledge={"auto_install": True})
    commit_files(repo, **SOURCES)
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **{**INTENT_BODY, "Affected users and systems": "`src/web/api.py`"})
    assert run("plan", "accept")["ok"]
    run("design", "new")
    fill(repo / "crewforge5/feat/spec.md", **{"Requirements": "r", "Design": "d", "Concerns": "none", "Open questions": "none", "Proof": "tests"})
    assert run("design", "accept")["ok"]
    run("build", "new")
    fill(repo / "crewforge5/feat/plan.md", **{**PLAN_BODY, "Files that change": "- src/web/api.py\n- tests/test_feat.py (new)"})
    assert run("knowledge", "bootstrap")["ok"]
    commit_files(repo, "artifacts")


def test_build_accept_requires_a_build_pack_at_head(run, repo: Path, packs, toml_config):
    """R-K3: `build accept` is refused without a build pack at HEAD; a new commit makes the pack stale."""
    accepted_spec_with_graph(run, repo, toml_config)
    out = run("build", "accept")
    assert out["ok"] is False and "no build context pack" in out["reason"] and out["next"] == "crewforge5 knowledge pack build --slug feat"
    assert "Status: draft" in (repo / "crewforge5/feat/plan.md").read_text()
    assert pack(run, "build")["ok"]
    commit_files(repo, "later", **{"notes.txt": "n\n"})
    subprocess.run(["graphify", "update", "."], cwd=repo, check=True, capture_output=True)
    stale = run("build", "accept")
    assert stale["ok"] is False and "not HEAD" in stale["reason"]
    assert pack(run, "build")["ok"]
    accepted = run("build", "accept")
    assert accepted["ok"] and accepted["pack"]["files"] >= 1


def test_review_review_requires_a_review_pack_covering_every_change(run, repo: Path, accepted_plan, packs, toml_config):
    """R-K3: `review review` needs a review pack at HEAD accounting for every changed text file."""
    toml_config(knowledge={"auto_install": True}, commands={"test": "exit 1"})
    commit_files(repo, **SOURCES)
    assert run("knowledge", "bootstrap")["ok"]
    commit_files(repo, "bootstrap")
    subprocess.run(["git", "checkout", "-qb", "feat"], cwd=repo, check=True)
    for step in ("1", "2"):
        toml_config(knowledge={"auto_install": True}, commands={"test": "exit 1"})
        assert run("build", "red", step)["ok"]
        toml_config(knowledge={"auto_install": True}, commands={"test": "exit 0"})
        assert run("build", "green", step)["ok"]
    regraph(repo, **{"src__web__api.py": "a = 2\n"})
    assert run("review", "run")["ok"]
    (repo / "crewforge5/feat/review.md").write_text("# Review\n\n## Bugs\n- none\n\n## Security\n- none\n\n## Compliance\n- none\n")
    out = run("review", "review")
    assert out["ok"] is False and "no review context pack" in out["reason"]
    built = pack(run, "review")
    assert built["ok"] and "src/web/api.py" in built["files"]
    assert run("review", "review")["ok"]
