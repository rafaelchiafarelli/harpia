"""The Python AuditSink runtime (python-target / py-foundation task 4):
``Compliance/runtime/python/audit_sink.py``, the port of Foundation F3's
``harpia_audit_sink.h``.

Pure Python: ``record``'s parameter names and order match the C++
declaration (parsed from the header, not hard-coded); the ABC can't be
instantiated; ``NoOpAuditSink.record`` is side-effect free;
``default_audit_sink()`` is the same object on every call; a subclass sees
exactly the tuples it was given; ``copy_runtime_module`` lands it at
``harpia_runtime.compliance.audit_sink`` with an importable package.

Image-gated: the copied module passes the task-3 gate (mypy --strict, ruff,
sphinx-build -W with the module in api.rst).
"""
import importlib.util
import inspect
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Compliance.audit_common import (AUDIT_SINK_RUNTIME_SRC,  # noqa: E402
                                     PY_AUDIT_SINK_MODULE,
                                     PY_AUDIT_SINK_RUNTIME_SRC)
from PyAdapter.runtime_copy import copy_runtime_module  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location("py_audit_sink",
                                                  PY_AUDIT_SINK_RUNTIME_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


audit = _load()


def test_record_signature_matches_cpp():
    header = open(AUDIT_SINK_RUNTIME_SRC).read()
    m = re.search(r"virtual void record\(([^)]*)\)\s*=\s*0;", header)
    cpp_names = re.findall(r"std::string&\s*(\w+)", m.group(1))
    sig = inspect.signature(audit.AuditSink.record)
    py_names = [p for p in sig.parameters if p != "self"]
    assert py_names == cpp_names == ["operation", "subject", "detail"]
    assert sig.parameters["detail"].default == ""
    for name in py_names:
        assert sig.parameters[name].annotation in (str, "str")


def test_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        audit.AuditSink()


def test_noop_records_nothing():
    sink = audit.NoOpAuditSink()
    assert sink.record("phi_read", "users.name") is None
    assert sink.record(operation="x", subject="y", detail="z") is None
    assert vars(sink) == {}


def test_default_sink_is_a_singleton_noop():
    a = audit.default_audit_sink()
    assert a is audit.default_audit_sink()
    assert isinstance(a, audit.NoOpAuditSink)


def test_subclass_sees_exact_tuples():
    class Recording(audit.AuditSink):
        def __init__(self):
            self.events = []

        def record(self, operation, subject, detail=""):
            self.events.append((operation, subject, detail))

    sink = Recording()
    sink.record("phi_write", "lab_result.value")
    sink.record("key_rotate", "kek:2", detail="ok")
    sink.record(operation="queue_rotated", subject="alarm_event", detail="seq=4")
    assert sink.events == [("phi_write", "lab_result.value", ""),
                           ("key_rotate", "kek:2", "ok"),
                           ("queue_rotated", "alarm_event", "seq=4")]


def test_copy_runtime_module_lands_importable(tmp_path):
    dest = str(tmp_path)
    target = copy_runtime_module(dest, PY_AUDIT_SINK_RUNTIME_SRC, PY_AUDIT_SINK_MODULE)
    py_root = os.path.join(dest, "python")
    assert target == os.path.join(py_root, "harpia_runtime", "compliance",
                                  "audit_sink.py")
    for pkg in ("harpia_runtime", os.path.join("harpia_runtime", "compliance")):
        assert os.path.isfile(os.path.join(py_root, pkg, "__init__.py"))
    mtime = os.stat(target).st_mtime_ns
    copy_runtime_module(dest, PY_AUDIT_SINK_RUNTIME_SRC, PY_AUDIT_SINK_MODULE)
    assert os.stat(target).st_mtime_ns == mtime
    r = subprocess.run(
        [sys.executable, "-c",
         "from harpia_runtime.compliance.audit_sink import default_audit_sink;"
         "print(type(default_audit_sink()).__name__)"],
        cwd=py_root, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "NoOpAuditSink", r.stderr


def _importable(*mods):
    try:
        for m in mods:
            importlib.import_module(m)
        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in
        ("mypy", "ruff", "sphinx-build", "protoc", "grpc_python_plugin"))
    or not _importable("google.protobuf", "grpc"),
    reason="Python quality-gate toolchain not installed (runs in the harpia-build image)")
def test_copied_module_passes_the_gate(tmp_path):
    from UnitTests._java_gradle_helpers import generate
    from PyAdapter.PyDocsAdapter import PyDocsAdapter
    out = generate(tmp_path, lang="python")
    copy_runtime_module(out, PY_AUDIT_SINK_RUNTIME_SRC, PY_AUDIT_SINK_MODULE)
    PyDocsAdapter(messages=[], dest=out).Process()
    py_root = os.path.join(out, "python")
    assert PY_AUDIT_SINK_MODULE in open(os.path.join(py_root, "docs", "api.rst")).read()
    for cmd in (["mypy", "--no-incremental"], ["ruff", "check", "--no-cache", "."],
                ["sphinx-build", "-q", "-W", "-E", "docs", str(tmp_path / "html")]):
        r = subprocess.run(cmd, cwd=py_root, capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, " ".join(cmd) + "\n" + r.stdout + r.stderr
