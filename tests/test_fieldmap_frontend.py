"""End-to-end (front-end only) coverage of the FieldMap freeze wired into
message.Message.Process -- runs the real pre_lex/lexer/MessageCreator
pipeline (via run_frontend.py, one fresh process per run, same convention as
test_frontend.py) and inspects the sidecar it leaves behind next to the
source file.

Complements tests/test_fieldmap.py (which drives message.FieldMap.freeze
directly): this confirms the wiring in message/Message.py actually calls it,
end to end, on real .harpia source across two generations.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_frontend.py")

sys.path.insert(0, REPO_ROOT)
from message.FieldMap import registry_path, _load


def _run(src, dest):
    r = subprocess.run(
        [sys.executable, RUNNER, str(src), str(dest)],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, "front-end runner crashed:\n" + r.stdout + r.stderr
    results = [ln[len("RESULT "):] for ln in r.stdout.splitlines()
               if ln.startswith("RESULT ")]
    assert len(results) == 1, "expected one RESULT line, got:\n" + r.stdout
    return results[0]


def test_field_numbers_survive_reorder_across_two_real_generations(tmp_path):
    src = tmp_path / "case.harpia"
    dest = tmp_path / "dest"

    src.write_text("message m {\nint a;\nint b;\n};\n", encoding="utf-8")
    assert _run(src, dest) == "OK"

    path = registry_path(str(src), "m")
    numbers, _ = _load(path)
    aNum, bNum = numbers["a"], numbers["b"]
    assert aNum != bNum

    # second generation: b declared before a, plus a new field c.
    src.write_text("message m {\nint b;\nint c;\nint a;\n};\n", encoding="utf-8")
    assert _run(src, dest) == "OK"

    numbers, reserved = _load(path)
    assert numbers["a"] == aNum
    assert numbers["b"] == bNum
    assert numbers["c"] not in (aNum, bNum)
    assert reserved == set()


def test_deleted_field_number_not_reused_across_two_real_generations(tmp_path):
    src = tmp_path / "case.harpia"
    dest = tmp_path / "dest"

    src.write_text("message m {\nint a;\nint b;\n};\n", encoding="utf-8")
    assert _run(src, dest) == "OK"
    path = registry_path(str(src), "m")
    numbers, _ = _load(path)
    aNum = numbers["a"]

    # "a" removed, "c" added.
    src.write_text("message m {\nint b;\nint c;\n};\n", encoding="utf-8")
    assert _run(src, dest) == "OK"

    numbers, reserved = _load(path)
    assert "a" not in numbers
    assert aNum in reserved
    assert numbers["c"] != aNum
