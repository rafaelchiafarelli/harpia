"""transitive-imports-DEFECT task 1: the generated module set is the
transitive closure of the root's imports, each file once.

- nested: root -> a.harpia -> b.harpia; B is generated (it used to be
  silently skipped);
- diamond: root -> a, c; a -> b; c -> b; B is generated once, no error;
- cycle: a -> b -> a is a generation error naming the cycle.

Pure Python (runs main.py in a subprocess).
"""
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)


def _msg(name):
    return "message {n} {{\n    required string label;\n}} {n}_table;\n".format(n=name)


def _generate(tmp_path, root_text, modules):
    inc = tmp_path / "Include"
    inc.mkdir()
    for fname, text in modules.items():
        (inc / fname).write_text(text)
    root = tmp_path / "root.harpia"
    root.write_text(root_text)
    out = tmp_path / "out"
    env = dict(os.environ, HARPIA_OUTPUT_DIR=str(out), HARPIA_INPUT_FILE=str(root),
               HARPIA_INCLUDE_FOLDER=str(inc))
    env.pop("HARPIA_GEN_LANG", None)
    r = subprocess.run([sys.executable, "main.py"], cwd=REPO_ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    h = hashlib.md5(root.read_bytes()).hexdigest()
    return r, out, h


def _proto(out, name, h):
    return os.path.join(str(out), "proto", "protofiles", "{}_{}.proto".format(name, h))


def test_nested_import_is_generated(tmp_path):
    r, out, h = _generate(tmp_path, 'import "a.harpia";\n', {
        "a.harpia": 'import "b.harpia";\n' + _msg("alpha"),
        "b.harpia": _msg("beta"),
    })
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert os.path.exists(_proto(out, "alpha", h))
    assert os.path.exists(_proto(out, "beta", h)), "nested import not generated"


def test_diamond_import_generates_once(tmp_path):
    r, out, h = _generate(tmp_path, 'import "a.harpia";\nimport "c.harpia";\n', {
        "a.harpia": 'import "b.harpia";\n' + _msg("alpha"),
        "c.harpia": 'import "b.harpia";\n' + _msg("gamma"),
        "b.harpia": _msg("beta"),
    })
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    for name in ("alpha", "beta", "gamma"):
        assert os.path.exists(_proto(out, name, h)), name


def test_import_cycle_is_an_error(tmp_path):
    r, _, _ = _generate(tmp_path, 'import "a.harpia";\n', {
        "a.harpia": 'import "b.harpia";\n' + _msg("alpha"),
        "b.harpia": 'import "a.harpia";\n' + _msg("beta"),
    })
    assert r.returncode != 0
    assert "IMPORT_CYCLE" in r.stdout, r.stdout[-3000:]
    assert "a.harpia" in r.stdout and "b.harpia" in r.stdout
