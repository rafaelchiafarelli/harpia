"""versioning epic / task 1 -- git fork-tracking metadata collection.

`collect_git_state()` reads the active git state of the schema project being
generated and returns it in a fixed six-field shape:

    {commit, ref, dirty, describe, origin_url, parent_commit}

Every field is guarded independently. A missing `git` binary, a directory
that is not a repository, or a subcommand that exits non-zero yields the
string ``"unknown"`` for that field (``dirty`` included) -- never an
omission, never a fabricated value, never a raise. This graceful-absence
behaviour is a contract, tested in its own right (see
``UnitTests/test_gitstate.py``), not merely a fallback.

Task 2 of the versioning epic emits these fields as ``harpia:git_*``
properties inside ``ComplianceReport/``'s ``bom.json``.

`git` is shelled out to (not a hand-rolled ``.git/`` reader) because the
fork-point field needs ``git merge-base``; ``git`` is an installed Docker
image dependency for this reason.
"""
import os
import subprocess

#: value for any field that could not be determined
UNKNOWN = "unknown"

#: the fixed key order of the dict collect_git_state() returns
FIELDS = ("commit", "ref", "dirty", "describe", "origin_url", "parent_commit")

_TIMEOUT_S = 10


def _run(args, cwd):
    """Run ``git <args>`` in ``cwd``. Return stripped stdout on success (may
    be an empty string), or ``None`` on any failure -- git absent, not a
    repo, non-zero exit, or timeout. An empty string is therefore
    "ran, no output" and is distinct from ``None`` = "failed"."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def collect_git_state(start_path=None):
    """Return the active git state as a fixed six-field dict (see module
    docstring for the graceful-absence contract).

    ``start_path`` defaults to ``os.getcwd()``; callers pass the input
    schema file's directory (a file path is accepted -- its directory is
    used). ``git`` itself walks upward from there to find the repository
    root, so worktrees / submodules / packed refs are handled for free.
    """
    cwd = start_path or os.getcwd()
    if not os.path.isdir(cwd):
        cwd = os.path.dirname(cwd) or "."

    def field(out):
        return out if out else UNKNOWN

    ref = _run(["symbolic-ref", "--short", "-q", "HEAD"], cwd)
    if not ref:  # detached HEAD -- try an exact tag match
        ref = _run(["describe", "--tags", "--exact-match"], cwd)

    porcelain = _run(["status", "--porcelain"], cwd)
    dirty = UNKNOWN if porcelain is None else bool(porcelain)

    return {
        "commit": field(_run(["rev-parse", "HEAD"], cwd)),
        "ref": field(ref),
        "dirty": dirty,
        "describe": field(_run(["describe", "--tags", "--always", "--dirty"], cwd)),
        "origin_url": field(_run(["config", "--get", "remote.origin.url"], cwd)),
        "parent_commit": field(_run(["merge-base", "HEAD", "origin/HEAD"], cwd)),
    }
