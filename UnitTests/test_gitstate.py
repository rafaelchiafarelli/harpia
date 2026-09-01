"""versioning epic / task 1 -- Util/gitstate.collect_git_state().

Pure Python, always run. The cases that need a real `git` binary are
skipif-gated (same discipline as the protoc/cmake behavioural tests); the
graceful-absence cases run everywhere, including in an image without git.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Util.gitstate import collect_git_state, FIELDS, UNKNOWN

needs_git = pytest.mark.skipif(shutil.which("git") is None,
                               reason="git binary not on PATH")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _init_repo(path):
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "commit.gpgsign", "false")


def _commit(path, name, body="x\n"):
    (path / name).write_text(body)
    _git(path, "add", name)
    _git(path, "commit", "-q", "-m", "add " + name)


# -- shape + graceful absence (always run) ---------------------------------

def test_shape_is_exactly_the_six_fields():
    assert tuple(collect_git_state().keys()) == FIELDS


def test_non_repo_dir_is_all_unknown(tmp_path):
    st = collect_git_state(str(tmp_path))
    assert st == {f: UNKNOWN for f in FIELDS}


def test_git_binary_absent_is_graceful(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(subprocess, "run", boom)
    st = collect_git_state(str(tmp_path))
    assert st == {f: UNKNOWN for f in FIELDS}


def test_subcommand_failure_is_graceful(tmp_path, monkeypatch):
    class Fail:
        returncode = 1
        stdout = ""
        stderr = "fatal: not a git repository"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Fail())
    st = collect_git_state(str(tmp_path))
    assert st == {f: UNKNOWN for f in FIELDS}


# -- against a real git repo ---------------------------------------------

@needs_git
def test_matches_this_repo_head():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    st = collect_git_state(REPO_ROOT)
    assert st["commit"] == head
    assert st["ref"] != UNKNOWN
    assert st["describe"] != UNKNOWN


@needs_git
def test_init_repo_without_remote(tmp_path):
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt")
    st = collect_git_state(str(tmp_path))
    assert len(st["commit"]) == 40 and st["commit"] != UNKNOWN
    assert st["ref"] != UNKNOWN                      # a branch name
    assert st["describe"] != UNKNOWN
    assert st["origin_url"] == UNKNOWN               # no remote configured
    assert st["parent_commit"] == UNKNOWN            # no origin/HEAD


@needs_git
def test_dirty_flag_tracks_worktree(tmp_path):
    _init_repo(tmp_path)
    _commit(tmp_path, "a.txt")
    assert collect_git_state(str(tmp_path))["dirty"] is False
    (tmp_path / "untracked.txt").write_text("dirty\n")
    assert collect_git_state(str(tmp_path))["dirty"] is True


@needs_git
def test_accepts_a_file_path_as_start(tmp_path):
    _init_repo(tmp_path)
    schema = tmp_path / "schema.harpia"
    _commit(tmp_path, "schema.harpia", "// schema\n")
    st = collect_git_state(str(schema))            # a file, not its dir
    assert st["commit"] != UNKNOWN


@needs_git
def test_parent_commit_is_the_fork_point(tmp_path):
    upstream = tmp_path / "upstream.git"
    upstream.mkdir()
    _git(upstream, "init", "-q", "--bare")

    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(upstream), "work")
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "Test")
    _git(work, "config", "commit.gpgsign", "false")
    _commit(work, "base.txt")
    _git(work, "push", "-q", "origin", "HEAD")
    _git(work, "remote", "set-head", "origin", "-a")   # make origin/HEAD resolve

    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(work),
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    _commit(work, "local.txt")                          # diverge from upstream

    st = collect_git_state(str(work))
    assert st["commit"] != base
    assert st["parent_commit"] == base                  # traceable to parent
    assert st["origin_url"] == str(upstream)
