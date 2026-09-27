"""R-C1/R-C2: one config file deep-merged over the defaults, one off switch per layer in config and env."""

from pathlib import Path

import pytest

from crewforge5 import project as p

README = Path(p.PLUGIN_ROOT / "README.md")


def test_defaults_without_a_file(repo):
    cfg = p.config(repo)
    assert cfg["project"]["home"] == "crewforge5"
    assert cfg["checkpoint"]["enabled"] is True
    assert cfg["build"]["require_adversarial_stamp"] is False


def test_file_deep_merges_over_defaults(repo, toml_config):
    toml_config(checkpoint={"paths": ["extra.txt"]})
    cfg = p.config(repo)
    assert cfg["checkpoint"]["paths"] == ["extra.txt"]
    assert cfg["checkpoint"]["enabled"] is True  # sibling key survives
    assert cfg["project"]["home"] == "crewforge5"


def test_config_is_a_copy(repo):
    p.config(repo)["project"]["home"] = "mutated"
    assert p.config(repo)["project"]["home"] == "crewforge5"


def test_invalid_toml_is_a_refusal(run, repo):
    (repo / ".crewforge5.toml").write_text("[project\n")
    out = run("status")
    assert out["ok"] is False and ".crewforge5.toml is not valid TOML" in out["reason"]


def test_first_new_creates_the_config(run, repo):
    assert not (repo / ".crewforge5.toml").exists()
    assert run("plan", "new", "Feat")["config_created"] is True
    assert (repo / ".crewforge5.toml").read_text() == p.DEFAULT_CONFIG
    assert run("plan", "new", "Other")["config_created"] is False


def test_the_config_file_is_read_in_one_function():
    readers = [f.name for f in Path(p.__file__).parent.glob("*.py") if "tomllib.load" in f.read_text()]
    assert readers == ["project.py"]
    assert Path(p.__file__).read_text().count("tomllib.loads(path") == 1


def test_home_is_configurable(run, repo, toml_config):
    toml_config(project={"home": "work/features"})
    run("plan", "new", "Feat")
    assert (repo / "work/features/feat/intent.md").exists()


def test_home_env_overrides_config(run, repo, monkeypatch):
    monkeypatch.setenv("CREWFORGE5_HOME", "elsewhere")
    run("plan", "new", "Feat")
    assert (repo / "elsewhere/feat/intent.md").exists()


@pytest.mark.parametrize("bad", ["/tmp/x", "..", "../out", "."])
def test_home_must_stay_inside_the_project(run, toml_config, bad):
    toml_config(project={"home": bad})
    out = run("plan", "new", "Feat")
    assert out["ok"] is False and "inside the project" in out["reason"]


@pytest.mark.parametrize("layer", p.LAYERS)
def test_every_layer_has_both_off_switches(repo, toml_config, monkeypatch, layer):
    monkeypatch.delenv(f"CREWFORGE5_{layer.upper()}", raising=False)
    assert p.enabled(repo, layer)
    monkeypatch.setenv(f"CREWFORGE5_{layer.upper()}", "off")
    assert not p.enabled(repo, layer)
    monkeypatch.delenv(f"CREWFORGE5_{layer.upper()}")
    toml_config(**{layer: {"enabled": False}})
    assert not p.enabled(repo, layer)


@pytest.mark.parametrize("layer", p.LAYERS)
def test_every_off_switch_is_documented_in_the_plugin_readme(layer):
    text = README.read_text()
    assert f"CREWFORGE5_{layer.upper()}=off" in text
    assert f"[{layer}] enabled = false" in text
