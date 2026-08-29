"""Tests for Track O, Session O.5 -- the KMS/HSM KeyProvider reference
adapter (Crypto/runtime/harpia_key_provider_kms.h).

O.5's bar: a second real-shaped backend (KmsKeyProvider, routed through the
KmsClient seam, driven here by the in-header MockKms reference) implements
Session O.1's KeyProvider interface with NO extra required hooks -- the
structural proof that swapping backends does not need interface changes.

Same compile-and-run C++ pattern as the other O.* tests. g++-gated.

Deferred (Track A's A.4, not faked here): write -> persist -> rotate KEK ->
read with no full re-encryption; swap default -> this adapter with zero DAO
changes.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

from Crypto.key_provider_common import (  # noqa: E402
    KEY_PROVIDER_KMS_RUNTIME_SRC, KEY_PROVIDER_KMS_RUNTIME_DEPS)

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ not available")


def _compile_and_run(tmp_path, body, name, extra_top=""):
    src = tmp_path / "{}.cpp".format(name)
    src.write_text(
        '#include "Crypto/runtime/harpia_key_provider_kms.h"\n'
        '#include <map>\n#include <string>\n'
        + extra_top
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


def test_common_module_paths_resolve():
    assert os.path.isfile(KEY_PROVIDER_KMS_RUNTIME_SRC)
    assert KEY_PROVIDER_KMS_RUNTIME_SRC.endswith("harpia_key_provider_kms.h")
    for _, dep_src in KEY_PROVIDER_KMS_RUNTIME_DEPS:
        assert os.path.isfile(dep_src)


def test_kms_provider_satisfies_the_keyprovider_contract(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    MockKms kms;
    KmsKeyProvider kp(kms);

    Dek d = kp.generate_dek();
    if (d.material.empty()) return 10;

    WrappedDek w = kp.wrap_dek(d);
    if (w.bytes == d.material) return 11;
    if (w.kek_version != 1) return 12;
    auto back = kp.unwrap_dek(w);
    if (!back.has_value() || back->material != d.material) return 13;

    const std::string pt = "spo2=97";
    if (d.open(d.seal(pt)) != pt) return 14;

    std::uint64_t v2 = kp.rotate();
    if (v2 != 2 || kp.active_kek_version() != 2) return 15;
    auto b1 = kp.unwrap_dek(w);                  // KMS keeps the old version
    if (!b1.has_value() || b1->material != d.material) return 16;

    Dek d2 = kp.generate_dek();
    WrappedDek w2 = kp.wrap_dek(d2);
    if (w2.kek_version != 2) return 17;

    WrappedDek missing{999, w.bytes};
    if (kp.unwrap_dek(missing).has_value()) return 18;
''', "kms_contract")
    assert r.returncode == 0, r.stdout + r.stderr


def test_kms_crypto_shred_and_kms_version_retirement(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    MockKms kms;
    KmsKeyProvider kp(kms);

    Dek d = kp.generate_dek();
    WrappedDek w = kp.wrap_dek(d);

    kp.shred_dek(w);                             // per-DEK shred (O.3), local
    if (kp.unwrap_dek(w).has_value()) return 20;

    // a different record is unaffected...
    Dek d2 = kp.generate_dek();
    WrappedDek w2 = kp.wrap_dek(d2);
    auto ok = kp.unwrap_dek(w2);
    if (!ok.has_value() || ok->material != d2.material) return 21;

    // ...until the KMS itself retires that key version
    kms.forget_version(w2.kek_version);
    if (kp.unwrap_dek(w2).has_value()) return 22;
''', "kms_shred")
    assert r.returncode == 0, r.stdout + r.stderr


def test_kms_provider_wires_audit(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    struct CountingSink : harpia::compliance::AuditSink {
        std::map<std::string,int> calls;
        void record(const std::string& op, const std::string&,
                    const std::string& = "") override { calls[op] += 1; }
    };

    CountingSink sink;
    MockKms kms;
    KmsKeyProvider kp(kms, sink);

    Dek d = kp.generate_dek();
    WrappedDek w = kp.wrap_dek(d);
    (void) kp.unwrap_dek(w);
    kp.rotate();
    kp.shred_dek(w);

    if (sink.calls["key_generate"] != 1) return 30;   // no ctor KEK: the KMS owns KEKs
    if (sink.calls["key_wrap"]     != 1) return 31;
    if (sink.calls["key_unwrap"]   != 1) return 32;
    if (sink.calls["key_rotate"]   != 1) return 33;
    if (sink.calls["key_shred"]    != 1) return 34;
''', "kms_audit")
    assert r.returncode == 0, r.stdout + r.stderr


def test_backends_are_interchangeable_through_the_interface(tmp_path):
    # the SAME round-trip code, byte-for-byte, run against InMemoryKeyProvider
    # and KmsKeyProvider held as a KeyProvider& -- O.5's "no interface
    # changes to swap backends" proof.
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider mem;
    if (int e = exercise(mem)) return 40 + e;

    MockKms kms;
    KmsKeyProvider adapter(kms);
    if (int e = exercise(adapter)) return 50 + e;
''', "kms_swap", extra_top='''
// harpia_key_provider_kms.h already pulls in harpia_key_provider.h
static int exercise(harpia::crypto::KeyProvider& kp) {
    using namespace harpia::crypto;
    Dek d = kp.generate_dek();
    WrappedDek w = kp.wrap_dek(d);
    auto back = kp.unwrap_dek(w);
    if (!back.has_value() || back->material != d.material) return 1;
    kp.rotate();
    auto still = kp.unwrap_dek(w);
    if (!still.has_value() || still->material != d.material) return 2;
    kp.shred_dek(w);
    if (kp.unwrap_dek(w).has_value()) return 3;
    return 0;
}
''')
    assert r.returncode == 0, r.stdout + r.stderr
