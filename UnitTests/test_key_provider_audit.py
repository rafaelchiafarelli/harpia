"""Tests for Track O, Session O.4 -- zeroization + AuditSink wiring.

O.4 adds two things to the KeyProvider runtime:
  - every key operation (generate / wrap / unwrap / rotate / shred) is
    routed through an injected harpia::compliance::AuditSink with a
    distinct operation name; the `subject` is identifying metadata only
    ("kek:<version>", "dek"), never key bytes (Rule 5, structural).
  - key material is wiped from memory when it stops being needed:
    detail::secure_zero(), the Dek destructor, KEK wipe on eviction / in
    the provider destructor.

Same compile-and-run C++ pattern as the other O.* tests (+ one pure-Python
scan). g++-gated for the C++ parts.
"""
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNTIME_DIR = os.path.join(REPO_ROOT, "Crypto", "runtime")

_GXX = shutil.which("g++")


def _compile_and_run(tmp_path, body, name, extra_top=""):
    src = tmp_path / "{}.cpp".format(name)
    src.write_text(
        '#include "Crypto/runtime/harpia_key_provider_local.h"\n'
        '#include <map>\n#include <string>\n#include <vector>\n'
        + _COUNTING_SINK + extra_top
        + "\nint main() {\n" + body + "\n    return 0;\n}\n",
        encoding="utf-8",
    )
    binpath = tmp_path / name
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", REPO_ROOT,
         "-I", os.path.join(REPO_ROOT, "Compliance", "runtime"),
         str(src), "-o", str(binpath)],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    return subprocess.run([str(binpath)], capture_output=True, text=True)


def _store(tmp_path):
    return str(tmp_path / "keks.store").replace("\\", "/")


# An AuditSink that tallies calls per operation and keeps every
# (subject, detail) pair it was handed, so a test can assert both the count
# and that key bytes never reach the sink.
_COUNTING_SINK = '''
struct CountingSink : harpia::compliance::AuditSink {
    std::map<std::string, int> calls;
    std::vector<std::string> subjects;
    std::vector<std::string> details;
    void record(const std::string& op, const std::string& subject,
                const std::string& detail = "") override {
        calls[op] += 1;
        subjects.push_back(subject);
        details.push_back(detail);
    }
};
'''


# ---- pure Python: no hardcoded key material in the headers --------------

def test_no_hardcoded_key_material_in_runtime_headers():
    # "mechanically checkable: no raw key material in source" -- a long
    # hex/base64 run in a string or char literal would be a red flag.
    long_hex = re.compile(r'["\'][0-9a-fA-F]{32,}["\']')
    long_b64 = re.compile(r'["\'][A-Za-z0-9+/]{40,}={0,2}["\']')
    for name in sorted(os.listdir(RUNTIME_DIR)):
        if not name.endswith(".h"):
            continue
        text = open(os.path.join(RUNTIME_DIR, name)).read()
        assert not long_hex.search(text), "{}: hex literal that could be a key".format(name)
        assert not long_b64.search(text), "{}: base64 literal that could be a key".format(name)


# ---- C++: AuditSink wiring ---------------------------------------------

@pytest.mark.skipif(_GXX is None, reason="g++ not available")
def test_each_key_op_emits_exactly_one_audit_record(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    CountingSink sink;
    InMemoryKeyProvider kp(sink);          // ctor mints + audits KEK v1

    Dek d = kp.generate_dek();             // key_generate  (#2)
    WrappedDek w = kp.wrap_dek(d);         // key_wrap
    (void) kp.unwrap_dek(w);               // key_unwrap
    kp.rotate();                           // key_rotate
    kp.shred_dek(w);                       // key_shred

    if (sink.calls["key_generate"] != 2) return 10;   // ctor KEK + generate_dek
    if (sink.calls["key_wrap"]     != 1) return 11;
    if (sink.calls["key_unwrap"]   != 1) return 12;
    if (sink.calls["key_rotate"]   != 1) return 13;
    if (sink.calls["key_shred"]    != 1) return 14;
''', "audit_counts")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(_GXX is None, reason="g++ not available")
def test_local_provider_also_wires_audit(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    CountingSink sink;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    LocalKeyProvider kp(cfg, sink);        // fresh store -> audits KEK v1

    kp.shred_dek(kp.wrap_dek(kp.generate_dek()));
    if (sink.calls["key_generate"] != 2) return 20;
    if (sink.calls["key_wrap"]     != 1) return 21;
    if (sink.calls["key_shred"]    != 1) return 22;
''' % _store(tmp_path), "audit_local")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(_GXX is None, reason="g++ not available")
def test_audit_subject_and_detail_never_carry_key_bytes(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    CountingSink sink;
    InMemoryKeyProvider kp(sink);

    Dek d = kp.generate_dek();
    WrappedDek w = kp.wrap_dek(d);
    (void) kp.unwrap_dek(w);
    kp.rotate();
    kp.shred_dek(w);
    // an unknown-version unwrap too (its own audited branch)
    WrappedDek bogus{999, w.bytes};
    (void) kp.unwrap_dek(bogus);

    auto ok_subject = [](const std::string& s) {
        return s == "dek" || s.rfind("kek:", 0) == 0;   // "kek:<n>"
    };
    auto ok_detail = [](const std::string& s) {
        return s.empty() || s == "ok" || s == "shredded" || s == "unknown_version";
    };
    for (const auto& s : sink.subjects) if (!ok_subject(s)) return 30;
    for (const auto& s : sink.details)  if (!ok_detail(s))  return 31;

    // and never the actual DEK / wrapped bytes
    for (const auto& s : sink.subjects) {
        if (s == d.material || s == w.bytes) return 32;
    }
''', "audit_no_bytes")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(_GXX is None, reason="g++ not available")
def test_default_audit_sink_when_none_passed(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;                // no sink -> default_audit_sink() (no-op)
    auto back = kp.unwrap_dek(kp.wrap_dek(kp.generate_dek()));
    if (!back.has_value()) return 40;
    kp.rotate();
    kp.shred_dek(WrappedDek{1, "x"});
''', "audit_default")
    assert r.returncode == 0, r.stdout + r.stderr


# ---- C++: zeroization --------------------------------------------------

@pytest.mark.skipif(_GXX is None, reason="g++ not available")
def test_secure_zero_clears_the_string(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    std::string s(32, 'K');
    detail::secure_zero(s);
    if (!s.empty()) return 50;
    std::string empty;
    detail::secure_zero(empty);            // must be safe on an empty string
''', "secure_zero")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(_GXX is None, reason="g++ not available")
def test_dek_opts_into_custom_cleanup(tmp_path):
    # Dek is no longer trivially destructible -- it has the zeroizing dtor.
    r = _compile_and_run(tmp_path, '''
    #include <type_traits>
    using namespace harpia::crypto;
    static_assert(!std::is_trivially_destructible<Dek>::value,
                  "Dek must run a zeroizing destructor (O.4)");
    // still usable as a value type (needed for std::optional<Dek> and the
    // wrap/unwrap return path)
    static_assert(std::is_move_constructible<Dek>::value, "Dek must move");
    static_assert(std::is_copy_constructible<Dek>::value, "Dek must copy");
    Dek a(std::string(32, 'x'));
    Dek b = a;                             // copy
    Dek c = std::move(b);                  // move
    if (c.material.size() != 32) return 60;
''', "dek_cleanup")
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(_GXX is None, reason="g++ not available")
def test_contract_still_holds_with_audit_and_zeroize(tmp_path):
    # the O.1 wrap/unwrap/rotate/shred round trip is behaviour-unchanged by
    # the O.4 additions, for both providers.
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;

    auto round_trip = [](KeyProvider& kp) -> int {
        Dek d = kp.generate_dek();
        WrappedDek w = kp.wrap_dek(d);
        auto back = kp.unwrap_dek(w);
        if (!back.has_value() || back->material != d.material) return 1;
        kp.rotate();
        auto still = kp.unwrap_dek(w);                 // old KEK retained
        if (!still.has_value() || still->material != d.material) return 2;
        kp.shred_dek(w);
        if (kp.unwrap_dek(w).has_value()) return 3;
        return 0;
    };

    CountingSink sink;
    InMemoryKeyProvider mem(sink);
    if (int e = round_trip(mem)) return 70 + e;

    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    LocalKeyProvider loc(cfg, sink);
    if (int e = round_trip(loc)) return 80 + e;
''' % _store(tmp_path), "audit_contract")
    assert r.returncode == 0, r.stdout + r.stderr
