"""Tests for Foundation F3 -- the AuditSink interface (stub).

Per initiatives/medical_devices/epics/thread-0-foundation/histories/
AuditSink-interface.md:
  - Unit: NoOpAuditSink.record() called, asserts no side effect, no crash.
  - Integration: instantiate and inject into a dummy generated class,
    confirm no build/runtime error.

The interface itself (Compliance/runtime/harpia_audit_sink.h) is hand-written
C++, not Python -- consistent with how it's actually used (injected into
*generated* code by later tracks), same pattern as
Capability/runtime/harpia_capability_dispatch.h. These tests compile and run
small C++ programs against it directly, with no generated project needed.
Skipped when g++ is absent (same convention as the other toolchain-gated
tests -- see tests/CLAUDE.md).
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

from Compliance.audit_common import AUDIT_SINK_RUNTIME_SRC

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ not available")


def _compile_and_run(tmp_path, cpp_source, name):
    src = tmp_path / "{}.cpp".format(name)
    src.write_text(cpp_source, encoding="utf-8")
    binpath = tmp_path / name
    compile_result = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-I", REPO_ROOT,
         str(src), "-o", str(binpath)],
        capture_output=True, text=True,
    )
    assert compile_result.returncode == 0, (
        "compile failed:\n" + compile_result.stdout + compile_result.stderr
    )
    return subprocess.run([str(binpath)], capture_output=True, text=True)


def test_runtime_header_file_exists():
    assert os.path.isfile(AUDIT_SINK_RUNTIME_SRC)
    assert AUDIT_SINK_RUNTIME_SRC.endswith("harpia_audit_sink.h")


def test_noop_audit_sink_record_has_no_side_effect_and_does_not_crash(tmp_path):
    r = _compile_and_run(tmp_path, '''
#include "Compliance/runtime/harpia_audit_sink.h"
int main() {
    harpia::compliance::NoOpAuditSink sink;
    sink.record("phi_read", "patient_123");
    sink.record("phi_write", "patient_123.heart_rate", "ok");
    return 0;
}
''', "noop_direct")
    assert r.returncode == 0, "exit {}\n".format(r.returncode) + r.stdout + r.stderr


def test_noop_audit_sink_called_through_base_class_reference(tmp_path):
    # the abstract interface is usable polymorphically -- exactly how
    # generated code will hold it (AuditSink&, not NoOpAuditSink directly).
    r = _compile_and_run(tmp_path, '''
#include "Compliance/runtime/harpia_audit_sink.h"
void do_audit(harpia::compliance::AuditSink& sink) {
    sink.record("key_rotate", "kek_1");
}
int main() {
    harpia::compliance::NoOpAuditSink sink;
    do_audit(sink);
    return 0;
}
''', "noop_polymorphic")
    assert r.returncode == 0, "exit {}\n".format(r.returncode) + r.stdout + r.stderr


def test_default_audit_sink_is_stable_and_usable(tmp_path):
    r = _compile_and_run(tmp_path, '''
#include "Compliance/runtime/harpia_audit_sink.h"
int main() {
    harpia::compliance::AuditSink& a = harpia::compliance::default_audit_sink();
    harpia::compliance::AuditSink& b = harpia::compliance::default_audit_sink();
    if (&a != &b) return 1;  // same shared instance every call
    a.record("message_sent", "AlarmEvent");
    return 0;
}
''', "default_sink")
    assert r.returncode == 0, "exit {}\n".format(r.returncode) + r.stdout + r.stderr


def test_injected_into_a_dummy_generated_class(tmp_path):
    # Integration: the documented injection-point pattern from the header's
    # own usage comment -- a generated-shaped class taking AuditSink& in its
    # constructor, defaulting to the shared no-op instance, calling
    # record() on a domain-specific operation it invented itself (never a
    # Foundation-owned enum).
    r = _compile_and_run(tmp_path, '''
#include "Compliance/runtime/harpia_audit_sink.h"
#include <string>

class some_dao {
public:
    explicit some_dao(harpia::compliance::AuditSink& audit =
                           harpia::compliance::default_audit_sink())
        : audit_(audit) {}
    void create(const std::string& value) {
        (void)value;  // never passed to record()
        audit_.record("phi_write", "some_dao.some_field");
    }
private:
    harpia::compliance::AuditSink& audit_;
};

int main() {
    // no sink passed -- must default cleanly
    some_dao default_injected;
    default_injected.create("sensitive-value-not-logged");

    // an explicit sink -- must also work
    harpia::compliance::NoOpAuditSink explicit_sink;
    some_dao explicitly_injected(explicit_sink);
    explicitly_injected.create("sensitive-value-not-logged");
    return 0;
}
''', "dummy_generated_class")
    assert r.returncode == 0, "exit {}\n".format(r.returncode) + r.stdout + r.stderr
