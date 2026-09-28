"""Spec §8 Proof: one fixture feature walked plan -> design -> build -> review on the CLI (R-S3, R-A3, R-T1, R-T2).

Each `new` is refused until the previous artifact is accepted, each accept (and `review review`) makes exactly one
checkpoint commit, and the commit log reads as plan(...), design(...), build(...), review(...).
"""

from conftest import INTENT_BODY, PLAN_BODY, SPEC_BODY, fill, git

FEAT = "crewforge5/feat"
REVIEW = "# Review: Feat\n\n## Bugs\n- none\n\n## Security\n- none\n\n## Compliance\n- Nit: name the helper (src/feat.py:1)\n"


def count(repo) -> int:
    return int(git(repo, "rev-list", "--count", "HEAD"))


def test_a_feature_walks_every_stage_with_one_checkpoint_per_boundary(run, repo, checkpoint_on, toml_config):
    stages = [("plan", "intent.md", INTENT_BODY), ("design", "spec.md", SPEC_BODY), ("build", "plan.md", PLAN_BODY)]
    assert run("plan", "new", "Feat")["ok"]
    for i, (stage, artifact, body) in enumerate(stages):
        if i:
            assert run(stage, "new")["ok"]
        if i + 1 < len(stages):
            later = stages[i + 1][0]
            refused = run(later, "new")
            assert refused["ok"] is False and f"{artifact} is not accepted" in refused["reason"]
        fill(repo / FEAT / artifact, **body)
        before = count(repo)
        assert run(stage, "accept")["ok"]
        assert count(repo) == before + 1, f"{stage} accept made {count(repo) - before} commits"

    # build: red then green for every Order-of-work step; review run refuses until both pairs exist
    toml_config(commands={"test": "exit 1"})
    assert run("build", "red", "1")["ok"]
    toml_config(commands={"test": "exit 0"})
    assert run("build", "green", "1")["ok"]
    assert run("review", "run")["ok"] is False
    toml_config(commands={"test": "exit 1"})
    assert run("build", "green", "2")["ok"] is False  # green before red is refused
    assert run("build", "red", "2")["ok"]
    toml_config(commands={"test": "exit 0"})
    assert run("build", "green", "2")["ok"]
    git(repo, "add", ".crewforge5.toml")
    git(repo, "commit", "-qm", "build(feat): steps 1-2")

    assert run("review", "run")["ok"]
    (repo / FEAT / "review.md").write_text(REVIEW)
    before = count(repo)
    assert run("review", "review")["ok"]
    assert count(repo) == before + 1

    subjects = git(repo, "log", "--format=%s").splitlines()
    assert [s.split("(", 1)[0] for s in subjects[:-1]] == ["review", "build", "build", "design", "plan"]
    assert subjects[0].startswith("review(feat): review — review.md")
    assert run("status", "--slug", "feat")["artifacts"] == {"intent.md": "accepted", "spec.md": "accepted", "plan.md": "accepted"}
