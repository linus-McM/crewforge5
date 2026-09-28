"""R-K5: Archify stage documents — config, render/check/open, the accept and review gates, skipped without Node."""

import json
from pathlib import Path

from conftest import INTENT_BODY, PLAN_BODY, SPEC_BODY, fill, sha256
from crewforge5 import artifacts, project

DISABLED = {"ok": True, "skipped": "docs disabled", "stage": "docs"}


def test_defaults_and_disabled_verdicts(run, repo: Path, toml_config, monkeypatch):
    conf = project.config(repo)["docs"]
    assert conf["enabled"] is True and conf["dir"] == "docs" and conf["quality"] == "showcase" and conf["open"] is True
    assert conf["types"] == {"plan": "architecture", "design": "dataflow", "build": "workflow", "review": "sequence"}
    for action in ("render", "check", "open"):
        assert run("docs", action, "plan") == DISABLED  # CREWFORGE5_DOCS=off from the repo fixture; no feature needed
    monkeypatch.delenv("CREWFORGE5_DOCS")
    toml_config(docs={"enabled": False})
    for action in ("render", "check", "open"):
        assert run("docs", action, "plan") == DISABLED


def source(repo: Path, stage: str, **extra) -> Path:
    path = repo / "crewforge5/feat/docs" / f"{stage}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "meta": {"title": stage, "quality_profile": "showcase"}, **extra}) + "\n")
    return path


def test_render_delivers_html_and_receipt(run, repo: Path, accepted_intent, docs_tools):
    src = source(repo, "plan")
    out = run("docs", "render", "plan")
    assert out["ok"], out
    html = repo / "crewforge5/feat/docs/plan.html"
    receipt = json.loads((repo / "crewforge5/feat/docs/plan.receipt.json").read_text())
    masked = (repo / "crewforge5/feat/intent.md").read_bytes().replace(b"Status: accepted", b"Status: -", 1)
    assert receipt["stage"] == "plan" and receipt["type"] == "architecture"
    assert receipt["sources"] == [{"resource": "crewforge5/feat/intent.md", "digest": sha256(masked)}]
    assert receipt["source_digest"] == sha256(b"crewforge5/feat/intent.md\n", masked)
    assert receipt["specification_sha256"] == sha256(src.read_bytes()) and receipt["artifact_sha256"] == sha256(html.read_bytes())
    assert receipt["validation"] == out["validation"] == "9/9 showcase, 0 errors, 0 warnings"
    assert docs_tools.calls()[-1] == f"node archify.mjs deliver architecture {src} {html} --quality showcase --json update_check=1"


def test_render_failures_are_verbatim(run, repo: Path, accepted_intent, docs_tools):
    out = run("docs", "render", "plan")
    assert not out["ok"] and out["reason"].startswith("stage document source missing; author crewforge5/feat/docs/plan.json")
    source(repo, "plan", fail=True)
    out = run("docs", "render", "plan")
    assert not out["ok"] and out["reason"] == "archify deliver exited 1: composition error: node budget"
    assert not (repo / "crewforge5/feat/docs/plan.receipt.json").exists()


def test_without_node_documents_are_skipped_not_failed(run, repo: Path, docs_tools, monkeypatch):
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    source(repo, "plan")
    docs_tools.uninstall("node")
    rendered = run("docs", "render", "plan")
    assert rendered["ok"] and "node >= 18 required" in rendered["skipped"]
    assert run("docs", "check", "plan")["skipped"] == rendered["skipped"]
    accepted = run("plan", "accept")
    assert accepted["ok"] and "node" in accepted["document"]["skipped"]


def test_check_reports_missing_fresh_and_stale(run, repo: Path, accepted_intent, docs_tools):
    out = run("docs", "check", "plan")
    assert not out["ok"] and out["reason"].startswith("stage document missing; author plan.json") and len(out["source_digest"]) == 64
    source(repo, "plan")
    assert run("docs", "render", "plan")["ok"]
    out = run("docs", "check", "plan")
    assert out["ok"] and out["fresh"] is True and out["artifact_matches"] is True
    intent = repo / "crewforge5/feat/intent.md"
    intent.write_text(intent.read_text() + "\nmore\n")
    out = run("docs", "check", "plan")
    assert not out["ok"] and out["reason"].startswith("stage document is stale: crewforge5/feat/intent.md changed since plan.html")
    assert out["next"] == "crewforge5 docs render plan --slug feat"
    assert run("docs", "check", "nope")["reason"].startswith("unknown stage 'nope'")


def test_accept_is_refused_while_the_document_is_missing_or_stale(run, repo: Path, docs_tools):
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    out = run("plan", "accept")
    assert not out["ok"] and out["reason"].startswith("stage document missing")
    assert artifacts.status((repo / "crewforge5/feat/intent.md").read_text()) == "draft"
    source(repo, "plan")
    assert run("docs", "render", "plan")["ok"] and run("plan", "accept")["ok"]
    assert run("docs", "check", "plan")["fresh"] is True  # the Status: line accept rewrites is masked
    run("design", "new")
    fill(repo / "crewforge5/feat/spec.md", **SPEC_BODY)
    source(repo, "design")
    assert run("docs", "render", "design")["ok"]
    spec = repo / "crewforge5/feat/spec.md"
    spec.write_text(spec.read_text() + "\nlater edit\n")
    out = run("design", "accept")
    assert not out["ok"] and out["reason"].startswith("stage document is stale: crewforge5/feat/spec.md")
    assert run("docs", "render", "design")["ok"] and run("design", "accept")["ok"]
    run("build", "new")
    fill(repo / "crewforge5/feat/plan.md", **PLAN_BODY)
    assert not run("build", "accept")["ok"]
    source(repo, "build")
    assert run("docs", "render", "build")["ok"]
    receipt = json.loads((repo / "crewforge5/feat/docs/build.receipt.json").read_text())
    assert receipt["type"] == "workflow" and run("build", "accept")["ok"]


def test_review_review_needs_the_sequence_document(run, repo: Path, accepted_plan, docs_tools, toml_config):
    for step in ("1", "2"):
        toml_config(commands={"test": "exit 1"})
        run("build", "red", step)
        toml_config(commands={"test": "exit 0"})
        run("build", "green", step)
    assert run("review", "run")["ok"]
    (repo / "crewforge5/feat/review.md").write_text("# Review\n\n## Bugs\n- none\n\n## Security\n- none\n\n## Compliance\n- none\n")
    out = run("review", "review")
    assert not out["ok"] and out["reason"].startswith("stage document missing; author review.json")
    source(repo, "review")
    assert run("docs", "render", "review")["ok"]
    receipt = json.loads((repo / "crewforge5/feat/docs/review.receipt.json").read_text())
    assert receipt["type"] == "sequence" and [s["resource"] for s in receipt["sources"]] == ["crewforge5/feat/review.md", "crewforge5/feat/test-report.json"]
    assert run("review", "review")["ok"]


def test_open_calls_the_opener_unless_ci_or_disabled(run, repo: Path, accepted_intent, docs_tools, toml_config, monkeypatch):
    source(repo, "plan")
    assert run("docs", "render", "plan")["ok"]
    out = run("docs", "open", "plan")
    assert out["ok"] and out["opened"] is True and docs_tools.calls()[-1].startswith("node open-artifact.mjs ")
    monkeypatch.setenv("CI", "1")
    calls = len(docs_tools.calls())
    out = run("docs", "open", "plan")
    assert out["ok"] and out["opened"] is False and out["note"] == "CI set" and len(docs_tools.calls()) == calls
    monkeypatch.delenv("CI")
    toml_config(docs={"open": False})
    assert run("docs", "open", "plan")["note"] == "[docs] open = false"


def test_dir_is_validated_and_receipts_are_data(run, repo: Path, accepted_intent, docs_tools, toml_config):
    from crewforge5 import docs

    toml_config(docs={"dir": "../outside"})
    out = run("docs", "render", "plan")
    assert not out["ok"] and out["reason"].startswith("[docs] dir '../outside' must be a relative path")
    toml_config(docs={"dir": "docs"})
    source(repo, "plan")
    assert run("docs", "render", "plan")["ok"]
    receipt = repo / "crewforge5/feat/docs/plan.receipt.json"
    receipt.write_text(receipt.read_text().replace("9/9 showcase, 0 errors, 0 warnings", "<script>alert(1)</script>"))
    assert docs.documents(repo, repo / "crewforge5/feat") == ["- plan: crewforge5/feat/docs/plan.html (unrecognised receipt)"]
    assert docs.validation({"validation": {"checksPassed": "9<b>", "checkCount": 9}}, "showcase") == "?/9 showcase, ? errors, ? warnings"


def test_documents_are_never_rendered_inside_a_hook():
    hooks = (project.PLUGIN_ROOT / "scripts/crewforge5/hooks.py").read_text()
    assert "docs" not in hooks.split('"""', 2)[2] and "archify" not in hooks.lower()


def test_stage_commands_carry_the_docs_step():
    step = (project.TEMPLATES / "docs-step.md").read_text()
    assert "Generated by CrewForge5 from" in step and "quality_profile" in step and "visual-check" in step
    for stage in ("plan", "design", "build", "review"):
        text = (project.PLUGIN_ROOT / "commands" / f"{stage}.md").read_text()
        kind = project.DEFAULTS["docs"]["types"][stage]
        assert f"crewforge5 docs render {stage}" in text and f"crewforge5 docs open {stage}" in text, stage
        assert f"Archify `{kind}`" in text and "templates/docs-step.md" in text, stage
    readme = (project.PLUGIN_ROOT / "README.md").read_text()
    assert "CREWFORGE5_DOCS=off" in readme and "npx -y skills add tt-a1i/archify" in readme
