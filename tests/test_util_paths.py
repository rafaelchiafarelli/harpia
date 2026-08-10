"""Path-resolution tests for Util.isFileInFolders.

isFileInFolders both (a) resolves bare import names (e.g. `file1.harpia`) against
a list of search folders and (b) accepts a path that already points at a real
file. Case (b) is what lets `run_harpia.sh` hand `main.py` an absolute input
path so the input .harpia can live anywhere on disk (before this, only paths
relative to a search folder resolved -- see run_frontend.py's chdir workaround).

Pure Python -- no C++ toolchain needed, runs on the host.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

from Util.util import isFileInFolders


def test_absolute_path_resolves_directly(tmp_path):
    f = tmp_path / "root.harpia"
    f.write_text("message m {\nint a;\n};\n", encoding="utf-8")
    # folders deliberately do NOT contain the file; the absolute path must win.
    ok, resolved = isFileInFolders([str(tmp_path / "nowhere")], str(f))
    assert ok is True
    assert resolved == str(f)


def test_relative_to_cwd_resolves_directly(tmp_path, monkeypatch):
    f = tmp_path / "root.harpia"
    f.write_text("message m {\nint a;\n};\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    ok, resolved = isFileInFolders([], "root.harpia")
    assert ok is True


def test_bare_name_found_in_search_folder(tmp_path):
    inc = tmp_path / "Include"
    inc.mkdir()
    (inc / "mod.harpia").write_text("message m {\nint a;\n};\n", encoding="utf-8")
    ok, resolved = isFileInFolders([str(tmp_path), str(inc)], "mod.harpia")
    assert ok is True
    assert resolved.endswith("Include/mod.harpia")


def test_missing_file_returns_error(tmp_path):
    ok, err = isFileInFolders([str(tmp_path)], "does_not_exist.harpia")
    assert ok is False
    assert err.errType.name == "IMPORT_INCOMPLETE_ERROR"
