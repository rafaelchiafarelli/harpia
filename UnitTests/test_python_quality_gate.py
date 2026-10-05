"""The quality gate for the generated Python tree (python-target /
py-foundation task 3): ``mypy --strict`` (``[tool.mypy]`` in the generated
``pyproject.toml``), ``ruff check`` (``[tool.ruff]``) and ``sphinx-build -W``
over ``docs/`` all exit 0 on the HarpiaTest fixture project.

Negative controls run the same gate on a temp copy with one deliberately bad
line injected (an untyped function, an unused import, a broken docstring),
so a gate that silently checks nothing can't pass.

Image-gated (mypy, ruff, sphinx-build, protoc + grpc_python_plugin, python
protobuf/grpcio).
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

from UnitTests._java_gradle_helpers import generate  # noqa: E402


def _importable(*mods):
    import importlib
    try:
        for m in mods:
            importlib.import_module(m)
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    any(shutil.which(t) is None for t in
        ("mypy", "ruff", "sphinx-build", "protoc", "grpc_python_plugin"))
    or not _importable("google.protobuf", "grpc"),
    reason="Python quality-gate toolchain not installed (runs in the harpia-build image)")


@pytest.fixture(scope="module")
def py_root(tmp_path_factory):
    out = generate(tmp_path_factory.mktemp("harpia_py_gate"), lang="python")
    return os.path.join(out, "python")


def _run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)


def _mypy(root):
    return _run(["mypy", "--no-incremental"], root)


def _ruff(root):
    return _run(["ruff", "check", "--no-cache", "."], root)


def _sphinx(root, out):
    return _run(["sphinx-build", "-q", "-W", "-E", "docs", str(out)], root)


def test_mypy_strict_passes(py_root):
    r = _mypy(py_root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Success" in r.stdout


def test_ruff_passes(py_root):
    r = _ruff(py_root)
    assert r.returncode == 0, r.stdout + r.stderr


def test_sphinx_builds_without_warnings(py_root, tmp_path):
    r = _sphinx(py_root, tmp_path / "html")
    assert r.returncode == 0, r.stdout + r.stderr
    api = (tmp_path / "html" / "api.html").read_text()
    assert "harpia_runtime" in api and "harpia_generated" in api


def test_mypy_config_is_strict(py_root):
    text = open(os.path.join(py_root, "pyproject.toml")).read()
    assert "strict = true" in text
    assert 'select = ["E", "F", "W", "I", "B", "UP"]' in text


def _bad_copy(py_root, tmp_path, line):
    dst = tmp_path / "python"
    shutil.copytree(py_root, dst)
    init = dst / "harpia_runtime" / "__init__.py"
    init.write_text(init.read_text() + line)
    return str(dst)


def test_negative_control_mypy(py_root, tmp_path):
    root = _bad_copy(py_root, tmp_path, "\n\ndef untyped(x):\n    return x\n")
    r = _mypy(root)
    assert r.returncode != 0 and "untyped" in r.stdout, r.stdout


def test_negative_control_ruff(py_root, tmp_path):
    root = _bad_copy(py_root, tmp_path, "\nimport os\n")
    r = _ruff(root)
    assert r.returncode != 0 and "F401" in r.stdout, r.stdout


def test_negative_control_sphinx(py_root, tmp_path):
    root = _bad_copy(py_root, tmp_path,
                     '\n\ndef documented() -> None:\n    """Broken *emphasis."""\n')
    r = _sphinx(root, tmp_path / "html")
    assert r.returncode != 0, r.stdout + r.stderr
