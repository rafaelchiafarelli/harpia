"""Regeneration is write-if-different, not a blanket wipe-and-rewrite (see
Util.util.write_if_different/copy_if_different/prune_stale_outputs, wired into
main.py). Nothing else in the suite runs the pipeline a *second* time against
the same persistent output dir, so this covers the two behaviors that only
show up across two runs:

  - an unchanged generated file must not be rewritten (mtime preserved), so a
    downstream cmake/make build can skip recompiling it instead of treating
    every regenerate as "everything changed".
  - a message renamed between two runs (root file's own text unchanged, so
    the md5 hash qualifying every filename stays the same -- the normal
    day-to-day workflow, editing an imported Include/ file) must have its old
    generated files removed, since nothing does a blanket wipe any more.

Uses a tiny inline two-file fixture (a root that imports one throwaway
include), not the shared HarpiaTest/Include fixtures, so it doesn't disturb
the pinned HASH constants documented in UnitTests/CLAUDE.md. Pure Python -- the
JSON adapter's text output is enough to verify both behaviors, no C++
toolchain required.
"""
import hashlib
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(root_file, output_dir):
    env = dict(os.environ, HARPIA_OUTPUT_DIR=output_dir,
               HARPIA_INPUT_FILE=root_file,
               HARPIA_INCLUDE_FOLDER=os.path.dirname(root_file))
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def _json_path(output_dir, name, root_hash):
    return os.path.join(output_dir, "generated", "cpp", "json",
                        "{}_{}_json.h".format(name, root_hash))


def test_unchanged_regen_preserves_mtime(tmp_path):
    # main.py currently requires at least one import (a root file with zero
    # imports hits an unrelated pre-existing bug: `analizer` is only bound
    # inside `for inc in listOfIncludes`), so route through one -- also just
    # matches how every real project is structured anyway.
    root = tmp_path / "root.harpia"
    root.write_text('import "inc.harpia";\n')
    inc = tmp_path / "inc.harpia"
    inc.write_text("message widget {\nint a;\n};\n")
    out = str(tmp_path / "out")
    root_hash = hashlib.md5(root.read_text().encode()).hexdigest()

    _run(str(root), out)
    generated = _json_path(out, "widget", root_hash)
    assert os.path.exists(generated), generated
    first_mtime = os.stat(generated).st_mtime_ns

    time.sleep(1.1)  # coarse filesystem mtime resolution safety margin
    _run(str(root), out)
    assert os.stat(generated).st_mtime_ns == first_mtime, (
        "unchanged content should not have been rewritten")


def test_renamed_message_prunes_old_files(tmp_path):
    root = tmp_path / "root.harpia"
    root.write_text('import "inc.harpia";\n')
    inc = tmp_path / "inc.harpia"
    inc.write_text("message widget {\nint a;\n};\n")
    out = str(tmp_path / "out")
    # md5 is over the ROOT file's own text only -- renaming the message
    # inside the imported inc.harpia below must not change this.
    root_hash = hashlib.md5(root.read_text().encode()).hexdigest()

    _run(str(root), out)
    old_file = _json_path(out, "widget", root_hash)
    assert os.path.exists(old_file), old_file

    inc.write_text("message gadget {\nint a;\n};\n")
    _run(str(root), out)
    new_file = _json_path(out, "gadget", root_hash)

    assert not os.path.exists(old_file), (
        "renamed-away message's old output should have been pruned")
    assert os.path.exists(new_file), new_file
