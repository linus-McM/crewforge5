"""R-K1, R-K4: the knowledge layer — bootstrap (check-only unless auto_install), status, refresh, check, shared bundle."""

import json
import subprocess
from pathlib import Path

import pytest

from conftest import INTENT_BODY, commit_files, fill
from crewforge5 import project as p

ACTIONS = ("bootstrap", "status", "refresh", "check")
STEP_NAMES = ["uv", "graphify", "skill", "graphifyignore", "graph", "repomix", "archify", "bundle"]


def states(out: dict) -> dict[str, str]:
    return {s["name"]: s["state"] for s in out["steps"]}


def test_defaults_and_disabled_verdicts(run, repo: Path, toml_config, monkeypatch):
    conf = p.config(repo)["knowledge"]
    assert conf["enabled"] is True and conf["auto_install"] is False and conf["bundle"] == ""
    assert "graphify-out/" in conf["ignore"]
    for action in ACTIONS:  # CREWFORGE5_KNOWLEDGE=off from the repo fixture
        assert run("knowledge", action) == {"ok": True, "skipped": "knowledge disabled", "stage": "knowledge"}
    monkeypatch.delenv("CREWFORGE5_KNOWLEDGE")
    toml_config(knowledge={"enabled": False})
    for action in ACTIONS:
        assert run("knowledge", action)["skipped"] == "knowledge disabled"


def test_frontmatter_subset_round_trip():
    from crewforge5 import knowledge as k

    data = {
        "type": "Feature",
        "title": "Claims: status page",
        "tags": ["feature", "accepted"],
        "generated": {"by": "crewforge5/0.4.5", "at": "2026-09-28T00:00:00Z"},
        "sources": [{"resource": "crewforge5/x/intent.md", "digest": "abc"}],
        "okf_version": "0.2",
    }
    text = k.dump_frontmatter(data) + "# Body\n"
    assert k.split_document(text) == (data, "# Body\n")
    assert k.split_document("no frontmatter\n") == ({}, "no frontmatter\n")
    front, _ = k.split_document("---\ntype: Feature\nweird: [unclosed\n---\nb\n")
    assert front["type"] == "Feature" and "_raw" in front


def test_bootstrap_is_check_only_by_default(run, repo: Path, knowledge):
    """Without auto_install nothing is installed: local builds run, missing tools are named with their install command."""
    out = run("knowledge", "bootstrap")
    assert [s["name"] for s in out["steps"]] == STEP_NAMES
    assert out["ok"] is False and out["mode"] == "build" and "graphify" in out["reason"] and "auto_install" in out["reason"]
    st = states(out)
    assert st["uv"] == "present" and st["graphify"] == "missing" and st["skill"] == "missing"
    assert st["graphifyignore"] == "built" and st["graph"] == "skipped" and st["bundle"] == "built"
    assert st["repomix"] == "skipped" and st["archify"] == "skipped"  # packs and docs are off in the repo fixture
    assert "uv tool install graphifyy" in next(s["detail"] for s in out["steps"] if s["name"] == "graphify")
    assert knowledge.calls() == []  # no installer ran
    assert "carry on without the graph" in out["next"]
    assert (repo / "crewforge5/knowledge/index.md").exists() and not (repo / "sdlc").exists()


def test_bootstrap_check_writes_nothing(run, repo: Path, knowledge):
    out = run("knowledge", "bootstrap", "check")
    assert out["ok"] is False and out["mode"] == "check"
    assert states(out)["graphifyignore"] == "missing" and states(out)["bundle"] == "missing"
    assert knowledge.calls() == [] and not (repo / ".graphifyignore").exists() and not (repo / "crewforge5").exists()


def test_bootstrap_installs_with_auto_install_then_is_idempotent(run, repo: Path, knowledge, toml_config, monkeypatch):
    toml_config(knowledge={"auto_install": True})
    out = run("knowledge", "bootstrap")
    assert out["ok"], out
    assert states(out) == {
        "uv": "present",
        "graphify": "installed",
        "skill": "installed",
        "graphifyignore": "built",
        "graph": "built",
        "repomix": "skipped",
        "archify": "skipped",
        "bundle": "built",
    }
    assert knowledge.calls() == ["uv tool install graphifyy", "graphify install --platform claude", "graphify update ."]
    assert knowledge.skill.exists() and (repo / "graphify-out/graph.json").exists()
    assert (repo / ".graphifyignore").read_text().splitlines() == p.config(repo)["knowledge"]["ignore"]
    assert out["next"] == "read crewforge5/knowledge/index.md before raw files"

    def boom(*a, **kw):
        raise AssertionError("subprocess used on a healthy project")

    monkeypatch.setattr(subprocess, "run", boom)
    again = run("knowledge", "bootstrap")
    assert again["ok"] and set(states(again).values()) == {"present", "skipped"}


def test_bootstrap_install_failure_is_reported(run, repo: Path, knowledge, toml_config):
    toml_config(knowledge={"auto_install": True})
    (knowledge.bin / "uv").write_text("#!/bin/sh\necho no network >&2\nexit 7\n")
    out = run("knowledge", "bootstrap")
    assert out["ok"] is False and "graphify failed" in out["reason"] and "no network" in out["reason"]


def test_uv_install_command_is_gated_by_operating_system():
    from crewforge5 import knowledge as k

    assert k.uv_install_command("Linux") == k.uv_install_command("Darwin") and "astral.sh/uv/install.sh" in k.uv_install_command("Linux")[-1]
    assert k.uv_install_command("Windows")[0] == "powershell"


def feature(run, repo: Path) -> Path:
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    return repo / "crewforge5/feat"


def test_refresh_builds_modules_and_features_and_is_idempotent(run, repo: Path, knowledge):
    feature(run, repo)
    commit_files(repo, "src")
    subprocess.run(["uv", "tool", "install", "graphifyy"], check=True)
    out = run("knowledge", "refresh")
    assert out["ok"] and out["bundle"] == "crewforge5/knowledge" and out["shared"] is False
    home = repo / "crewforge5/knowledge"
    assert sorted(f.name for f in (home / "modules").glob("*.md")) == ["api-py.md", "core-py.md", "fmt.md", "index.md"]
    concept = (home / "features/feat.md").read_text()
    assert concept.startswith("---\ntype: Feature\ntitle: Feat\n") and "resource: crewforge5/feat" in concept and "status: draft" in concept
    assert "- intent.md: draft" in concept
    index = (home / "index.md").read_text()
    assert 'okf_version: "0.2"' in index and "* [Feat](features/feat.md)" in index and "# Modules" in index and "graphify query" in index
    assert "- [api.py](/modules/api-py.md)" not in (home / "modules/core-py.md").read_text()
    assert "- [core.py](/modules/core-py.md)" in (home / "modules/api-py.md").read_text()  # api calls core: an EXTRACTED edge
    again = run("knowledge", "refresh")
    assert again["written"] == [] and again["unchanged"] == out["concepts"]


def test_status_and_check(run, repo: Path, knowledge, toml_config):
    toml_config(knowledge={"auto_install": True, "max_behind": 0})
    assert run("knowledge", "bootstrap")["ok"]
    commit_files(repo, "bootstrap output")
    out = run("knowledge", "status")
    assert out["ok"] is False and "commits behind HEAD" in out["reason"] and out["next"] == "crewforge5 knowledge refresh"
    assert run("knowledge", "refresh")["ok"]
    out = run("knowledge", "status")
    assert out["ok"], out
    assert out["graph"]["behind"] == 0 and out["bundle"]["concepts"] == 3
    assert run("knowledge", "check")["ok"]
    (repo / "crewforge5/knowledge/modules/broken.md").write_text("---\ntitle: x\n---\nbody\n")
    bad = run("knowledge", "check")
    assert bad["ok"] is False and bad["conformance"] == ["modules/broken.md: missing or empty `type`"]


def test_shared_cc_sdlc_bundle_is_read_and_written_not_duplicated(run, repo: Path, knowledge):
    """D2: with sdlc/knowledge/ present, CrewForge5 writes its feature concepts there and leaves the rest alone."""
    shared = repo / "sdlc/knowledge"
    (shared / "features").mkdir(parents=True)
    (shared / "modules").mkdir()
    (shared / "features/other.md").write_text("---\ntype: Feature\ntitle: Other\ndescription: cc_sdlc feature\nresource: sdlc/other\n---\nb\n")
    (shared / "modules/core.md").write_text("---\ntype: Module\ntitle: Core\nresource: src\n---\nm\n")
    (shared / ".state.json").write_text('{"commit": "abc"}\n')
    (shared / "index.md").write_text('---\nokf_version: "0.2"\n---\n# repo knowledge\n\nGenerated by the sdlc plugin.\n\n# Features\n* [Other](features/other.md) - cc_sdlc feature\n\n# Modules\n* [Core](modules/core.md) - m\n')
    feature(run, repo)
    out = run("knowledge", "refresh")
    assert out["ok"] and out["bundle"] == "sdlc/knowledge" and out["shared"] is True
    assert (shared / "features/feat.md").exists() and not (repo / "crewforge5/knowledge").exists()
    index = (shared / "index.md").read_text()
    assert "Generated by the sdlc plugin." in index and "* [Core](modules/core.md) - m" in index
    assert "* [Feat](features/feat.md)" in index and "* [Other](features/other.md) - cc_sdlc feature" in index
    assert (shared / ".state.json").read_text() == '{"commit": "abc"}\n' and (shared / "modules/core.md").read_text().endswith("m\n")
    assert run("knowledge", "status")["bundle"]["shared"] is True
    # a cc_sdlc feature with the same slug is never overwritten
    (shared / "features/feat.md").write_text("---\ntype: Feature\ntitle: Theirs\nresource: sdlc/feat\n---\nt\n")
    again = run("knowledge", "refresh")
    assert again["skipped_foreign"] == ["features/feat.md"] and "title: Theirs" in (shared / "features/feat.md").read_text()


@pytest.mark.parametrize("bad", ["../out", "/abs", "x/"])
def test_bundle_setting_is_validated(run, repo: Path, knowledge, toml_config, bad):
    toml_config(knowledge={"bundle": bad})
    out = run("knowledge", "refresh")
    assert out["ok"] is False and "[knowledge] bundle" in out["reason"]


def test_bundle_and_graph_output_are_never_plan_files(run, repo: Path, knowledge):
    from crewforge5 import build

    assert build.owned(repo, "crewforge5/knowledge/index.md") and build.owned(repo, "graphify-out/graph.json") and build.owned(repo, ".graphifyignore")
    (repo / "sdlc/knowledge").mkdir(parents=True)
    assert build.owned(repo, "sdlc/knowledge/features/x.md") and not build.owned(repo, "src/app.py")


def test_state_file_corruption_is_reported_not_raised(run, repo: Path, knowledge):
    home = repo / "crewforge5/knowledge"
    home.mkdir(parents=True)
    (home / ".crewforge5-state.json").write_text("<<<<<<< HEAD\n")
    out = run("knowledge", "status")
    assert out["ok"] is False and "unreadable" in out["reason"]
    assert json.loads(json.dumps(out))  # still one JSON verdict


def test_every_command_preamble_puts_knowledge_first():
    """R-K1: bootstrap, the knowledge index before raw files, graphify query/affected before grep."""
    preamble = (p.TEMPLATES / "command-preamble.md").read_text().strip()
    for clause in ("crewforge5 knowledge bootstrap", "check-only unless `[knowledge] auto_install = true`", "before raw files", "graphify query", "graphify affected", "before grep"):
        assert clause in preamble
    for name in ("init", "crew", "plan", "design", "build", "review"):
        body = (p.PLUGIN_ROOT / "commands" / f"{name}.md").read_text().split("\n---\n", 1)[1]
        assert body.startswith(preamble), name
