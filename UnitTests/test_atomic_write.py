"""Crash-safety of Util.util's write helpers (see
plans/crash-interrupt-recovery.md). write_if_different/copy_if_different
build the new file in a same-directory temp file, then os.replace() it into
place -- rename(2)/ReplaceFile are atomic, so a process killed at any point
either leaves the real path fully untouched (old content, or absent) or
fully updated, never truncated. These tests simulate the crash by making
os.replace raise partway through, which exercises the same "something went
wrong between the temp write and the rename" path a real kill would hit,
without the timing flakiness of an actual SIGKILL race.

Pure Python -- no C++ toolchain needed, runs on the host.
"""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

from Util.util import write_if_different, copy_if_different


def _boom(*_a, **_k):
    raise OSError("simulated crash between temp write and rename")


def test_write_if_different_new_file_crash_leaves_nothing_behind(tmp_path, monkeypatch):
    target = tmp_path / "out.txt"
    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        write_if_different(str(target), "new content")

    assert not target.exists()
    assert os.listdir(str(tmp_path)) == []


def test_write_if_different_existing_file_crash_preserves_old_content(tmp_path, monkeypatch):
    target = tmp_path / "out.txt"
    target.write_text("old content")
    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        write_if_different(str(target), "new content")

    assert target.read_text() == "old content"
    assert os.listdir(str(tmp_path)) == ["out.txt"]


def test_copy_if_different_crash_preserves_old_content(tmp_path, monkeypatch):
    src = tmp_path / "src.txt"
    src.write_text("new content")
    dst = tmp_path / "dst.txt"
    dst.write_text("old content")
    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        copy_if_different(str(src), str(dst))

    assert dst.read_text() == "old content"
    assert sorted(os.listdir(str(tmp_path))) == ["dst.txt", "src.txt"]


def test_write_if_different_success_leaves_no_temp_files(tmp_path):
    target = tmp_path / "out.txt"
    write_if_different(str(target), "content")
    assert os.listdir(str(tmp_path)) == ["out.txt"]
