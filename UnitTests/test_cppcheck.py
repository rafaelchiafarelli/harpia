"""static-fuzz-ci epic / task 1 -- cppcheck static-analysis gate.

Pure Python, `shutil.which`-gated on `cppcheck` (same discipline as
`test_doxygen_docs.py`). Generates the C++ tree via `run_pipeline.py` into
a tmp dir, runs `cppcheck --enable=warning,portability` over every
generated header, and asserts a clean exit. A finding not matched by
`UnitTests/cppcheck_suppressions.txt` fails the gate -- so this is a
regression net: the current tree is clean, and a future generator or
runtime-header change that introduces a warning-level defect breaks CI.

Scope note (see the task file): this is NOT the "CERT ruleset" originally
sketched -- upstream cppcheck removed the `cert` addon and the Ubuntu
package does not ship it. This is cppcheck's core warning/portability
analysis. `style` / `performance` are intentionally off (pure noise on
generated CRUDL code -- 50+ `shadowVariable` / `useStlAlgorithm`); a
follow-on task can tighten if wanted.

`UnitTests/cppcheck_suppressions.txt` is the baseline. cppcheck 2.13's
`--suppressions-list` parser rejects `#` comment lines ("Failed to add
suppression. No id."), so that file holds bare suppression ids ONLY --
one per line, `id` or `id:relative/path.h` or `id:path.h:line`. It
currently lists just `missingInclude` / `missingIncludeSystem` (inert at
warning/portability level; there is no protobuf/grpc/tinyxml2 include
tree -- not code defects). Add a line for a *confirmed* false positive
only, and note the reason in the commit / this docstring, not in the
file. Do not blanket-suppress a real finding -- fix it or scope a
follow-on.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
SUPPRESSIONS = os.path.join(HERE, "cppcheck_suppressions.txt")

pytestmark = pytest.mark.skipif(shutil.which("cppcheck") is None,
                                reason="cppcheck not on PATH")


def _generate(dest):
    proc = subprocess.run([sys.executable, RUNNER, str(dest)], cwd=REPO_ROOT,
                          capture_output=True, text=True)
    assert proc.returncode == 0, \
        "run_pipeline.py failed:\n{}\n{}".format(proc.stdout, proc.stderr)
    gen = os.path.join(str(dest), "build", "generated", "cpp")
    assert os.path.isdir(gen), "run_pipeline.py produced no generated/cpp tree"
    return gen


def test_cppcheck_warning_portability_is_clean(tmp_path):
    gen = _generate(tmp_path)

    headers = sorted(
        os.path.join(root, f)
        for root, _dirs, files in os.walk(gen)
        for f in files if f.endswith(".h")
    )
    assert headers, "no generated headers found to analyze"

    cmd = [
        "cppcheck",
        "--enable=warning,portability",
        "--language=c++", "--std=c++17",
        "--inline-suppr", "-q",
        "--error-exitcode=2",
        "--suppressions-list=" + SUPPRESSIONS,
        "--template={severity}: [{id}] {file}:{line}: {message}",
    ] + headers

    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(
            "cppcheck reported findings not in the baseline "
            "(exit {}).\n\nstdout:\n{}\n\nstderr:\n{}\n\n"
            "If the finding is real, fix it or scope a follow-on task; only "
            "add to {} for a confirmed false positive, with a reason.".format(
                proc.returncode, proc.stdout.strip(), proc.stderr.strip(),
                os.path.relpath(SUPPRESSIONS, REPO_ROOT)))
