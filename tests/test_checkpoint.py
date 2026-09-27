"""R-A3: every accept is one checkpoint commit of the plugin's own output, never of source or staged work."""

from pathlib import Path

from conftest import INTENT_BODY, PLAN_BODY, SPEC_BODY, fill, git
from crewforge5 import checkpoint
from crewforge5 import project as p


def subjects(repo: Path) -> list[str]:
    return git(repo, "log", "--format=%s").splitlines()


def files_in(repo: Path) -> list[str]:
    return sorted(git(repo, "show", "--name-only", "--format=", "HEAD").split())


def test_plan_accept_commits_the_intent_and_the_new_config(run, repo, checkpoint_on, accepted_intent):
    assert subjects(repo)[0] == "plan(feat): accept — intent.md (+1 file)"
    assert files_in(repo) == [".crewforge5.toml", "crewforge5/feat/intent.md"]
    assert p.changed_files(repo) == []


def test_each_accept_is_exactly_one_commit(run, repo, checkpoint_on, accepted_plan):
    assert subjects(repo) == [
        "build(feat): accept — plan.md",
        "design(feat): accept — spec.md",
        "plan(feat): accept — intent.md (+1 file)",
        "init",
    ]


def test_new_and_check_never_commit(run, repo, checkpoint_on):
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    run("plan", "check")
    assert subjects(repo) == ["init"]


def test_a_refused_accept_never_commits(run, repo, checkpoint_on):
    run("plan", "new", "Feat")
    out = run("plan", "accept")
    assert out["ok"] is False and "checkpoint" not in out
    assert subjects(repo) == ["init"]


def test_extra_generated_files_ride_along_and_are_counted(run, repo, checkpoint_on, accepted_spec):
    run("build", "new")
    (repo / "crewforge5/feat/notes.md").write_text("scratch\n")
    (repo / "crewforge5/feat/more.md").write_text("scratch\n")
    fill(repo / "crewforge5/feat/plan.md", **PLAN_BODY)
    assert run("build", "accept")["checkpoint"]["committed"] is True
    assert subjects(repo)[0] == "build(feat): accept — plan.md (+2 files)"


def test_source_changes_and_staged_work_are_never_swept_in(run, repo, checkpoint_on, accepted_intent):
    (repo / "src.py").write_text("half finished\n")
    (repo / "staged.py").write_text("staged\n")
    git(repo, "add", "staged.py")
    run("design", "new")
    fill(repo / "crewforge5/feat/spec.md", **SPEC_BODY)
    assert run("design", "accept")["ok"]
    assert files_in(repo) == ["crewforge5/feat/spec.md"]
    assert p.changed_files(repo) == ["src.py", "staged.py"]
    assert git(repo, "diff", "--cached", "--name-only") == "staged.py"


def test_checkpoint_paths_ride_along(run, repo, checkpoint_on, toml_config):
    toml_config(checkpoint={"paths": [".crewforge5.toml", "notes.txt"]})
    (repo / "notes.txt").write_text("n\n")
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    run("plan", "accept")
    assert files_in(repo) == [".crewforge5.toml", "crewforge5/feat/intent.md", "notes.txt"]


def test_env_off_switch(run, repo, accepted_intent):
    assert subjects(repo) == ["init"]  # the `repo` fixture sets CREWFORGE5_CHECKPOINT=off
    assert run("status", "--slug", "feat")["ok"]


def test_config_off_switch(run, repo, checkpoint_on, toml_config):
    toml_config(checkpoint={"enabled": False})
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    out = run("plan", "accept")
    assert out["checkpoint"] == {"ok": True, "committed": False, "skipped": "checkpoints disabled"}
    assert subjects(repo) == ["init"]


def test_nothing_to_commit_is_not_an_error(repo, checkpoint_on):
    out = checkpoint.commit(repo, "plan", "accept", repo / "crewforge5/feat/intent.md")
    assert out["ok"] is True and out["committed"] is False
    assert subjects(repo) == ["init"]


def test_a_merge_in_progress_skips_the_checkpoint(repo, checkpoint_on):
    (repo / "crewforge5/feat").mkdir(parents=True)
    (repo / "crewforge5/feat/intent.md").write_text("x\n")
    (repo / ".git/MERGE_HEAD").write_text(git(repo, "rev-parse", "HEAD") + "\n")
    out = checkpoint.commit(repo, "plan", "accept", repo / "crewforge5/feat/intent.md")
    assert out["committed"] is False and "in progress" in out["skipped"]
    assert subjects(repo) == ["init"]


def test_a_failed_commit_never_fails_the_stage(run, repo, checkpoint_on, monkeypatch):
    run("plan", "new", "Feat")
    fill(repo / "crewforge5/feat/intent.md", **INTENT_BODY)
    real = p.run_git
    monkeypatch.setattr(p, "run_git", lambda root, *args: real(root, "no-such-command") if args[0] == "commit" else real(root, *args))
    out = run("plan", "accept")
    assert out["ok"] is True and out["status"] == "accepted"
    assert out["checkpoint"]["ok"] is False and "git commit failed" in out["checkpoint"]["reason"]


def test_outside_git_the_stage_still_succeeds(tmp_path, monkeypatch):
    from crewforge5 import cli

    monkeypatch.delenv("CREWFORGE5_CHECKPOINT", raising=False)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    cli.main(["plan", "new", "Feat"], tmp_path)
    fill(tmp_path / "crewforge5/feat/intent.md", **INTENT_BODY)
    out = cli.main(["plan", "accept"], tmp_path)
    assert out["ok"] is True and out["checkpoint"]["committed"] is False
