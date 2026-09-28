"""Stage-boundary checkpoints (R-A3): after each accept and `review review`, `cli.main` commits the home directory and `[checkpoint] paths`.

The commit carries a pathspec, so source and tests stay out and work already staged in the index survives.
A checkpoint never decides the stage's verdict: `cli.main` reports a refusal under `checkpoint`.
"""

from __future__ import annotations

from pathlib import Path

from . import build
from . import project as p
from .project import fail

# The CLI's own bookkeeping (build.STATE) rides along with a boundary without counting as an extra file.
BOOKKEEPING = (build.STATE,)
IN_PROGRESS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")


def pending(root: Path) -> list[str]:
    """Changed files under the home directory or `[checkpoint] paths`; git-ignored files never appear."""
    return p.changed_files(root, p.rel(root, p.home(root)), *p.config(root)["checkpoint"]["paths"])


def busy(root: Path) -> bool:
    git_dir = root / p.git(root, "rev-parse", "--git-dir")  # per worktree, so a linked worktree's rebase is seen
    return any((git_dir / marker).exists() for marker in IN_PROGRESS)


def subject(root: Path, stage: str, action: str, produced: Path, files: list[str]) -> str:
    """`<stage>(<slug>): <action> — <artifact>`, plus ` (+N files)` for anything else that rides along."""
    scope = produced.parent.name if produced.parent != p.home(root) else ""
    extras = len([f for f in files if f != p.rel(root, produced) and Path(f).name not in BOOKKEEPING])
    tail = f" (+{extras} file{'s' if extras > 1 else ''})" if extras else ""
    return f"{stage}{f'({scope})' if scope else ''}: {action} — {produced.name}{tail}"


def commit(root: Path, stage: str, action: str, produced: Path) -> dict:
    """Commit what the boundary produced plus anything generated since the last one. Nothing to commit is a success."""
    if not p.enabled(root, "checkpoint"):
        return {"ok": True, "committed": False, "skipped": "checkpoints disabled"}
    if p.run_git(root, "rev-parse", "--git-dir").returncode != 0:
        return {"ok": True, "committed": False, "skipped": "not a git repository"}
    if busy(root):
        return {"ok": True, "committed": False, "skipped": "a merge, rebase, cherry-pick or revert is in progress"}
    if not (files := pending(root)):
        return {"ok": True, "committed": False, "skipped": "nothing to checkpoint"}
    message = subject(root, stage, action, produced, files)
    for argv in (["add", "--", *files], ["commit", "--no-verify", "-q", "-m", message, "--", *files]):
        result = p.run_git(root, *argv)
        if result.returncode != 0:
            fail(f"git {argv[0]} failed: {(result.stderr.strip().splitlines() or ['no output'])[-1]}", committed=False, message=message)
    return {"ok": True, "committed": True, "message": message, "files": files}
