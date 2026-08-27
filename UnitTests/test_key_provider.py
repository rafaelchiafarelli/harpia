"""Tests for Track O, Session O.1 -- the KeyProvider interface + envelope-
encryption shape (Crypto/runtime/harpia_key_provider.h).

Hand-written C++, not Python -- consistent with how it's used (injected into
*generated* DAO code by Track A), same pattern as
Compliance/runtime/harpia_audit_sink.h and harpia_delivery.h. These tests
compile and run small standalone C++ programs against the header directly,
no generated project needed. Skipped when g++ is absent.

Covers O.1's stated bar:
  - Unit: envelope wrap/unwrap round trip against the dummy impl.
  - Unit: rotation produces a new KEK version while existing DEKs remain
    unwrappable via their recorded version reference, and rotate() touches
    no existing WrappedDek (O(keys), not O(data)).
  - Rule 5: unwrap of a DEK whose KEK version is gone returns an empty
    optional -- a distinct, observable outcome, not a throw or a zeroed key
    (this is also the O.3 crypto-shred path, exercised early here).
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

from Crypto.key_provider_common import KEY_PROVIDER_RUNTIME_SRC  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ not available")


def _compile_and_run(tmp_path, body, name, extra_top=""):
    src = tmp_path / "{}.cpp".format(name)
    src.write_text(
        '#include "Crypto/runtime/harpia_key_provider.h"\n'
        '#include <string>\n'
        + extra_top
        + "\nint main() {\n" + body + "\n    return 0;\n}\n",
        encoding="utf-8",
    )
    binpath = tmp_path / name
    c = subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", REPO_ROOT,
         str(src), "-o", str(binpath)],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, "compile failed:\n" + c.stdout + c.stderr
    return subprocess.run([str(binpath)], capture_output=True, text=True)


def test_runtime_header_file_exists():
    assert os.path.isfile(KEY_PROVIDER_RUNTIME_SRC)
    assert KEY_PROVIDER_RUNTIME_SRC.endswith("harpia_key_provider.h")


def test_dek_wrap_unwrap_round_trip(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;

    Dek dek = kp.generate_dek();
    if (dek.material.empty()) return 10;

    WrappedDek w = kp.wrap_dek(dek);
    if (w.bytes == dek.material) return 11;        // wrapping changed the bytes

    auto back = kp.unwrap_dek(w);
    if (!back.has_value()) return 12;
    if (back->material != dek.material) return 13; // exact DEK recovered
''', "wrap_unwrap")
    assert r.returncode == 0, r.stdout + r.stderr


def test_dek_seals_and_opens_the_value(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;

    Dek dek = kp.generate_dek();
    const std::string plaintext = "patient heart_rate = 72 bpm";

    std::string sealed = dek.seal(plaintext);
    if (sealed == plaintext) return 20;           // value actually transformed

    // survives a wrap/unwrap of the DEK in between (envelope round trip)
    auto reopened_dek = kp.unwrap_dek(kp.wrap_dek(dek));
    if (!reopened_dek.has_value()) return 21;
    if (reopened_dek->open(sealed) != plaintext) return 22;
''', "seal_open")
    assert r.returncode == 0, r.stdout + r.stderr


def test_wrapped_dek_records_the_active_kek_version(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;
    if (kp.active_kek_version() != 1) return 30;   // starts at 1
    WrappedDek w = kp.wrap_dek(kp.generate_dek());
    if (w.kek_version != 1) return 31;             // stamped with the active version
''', "records_version")
    assert r.returncode == 0, r.stdout + r.stderr


def test_rotation_new_version_old_deks_still_unwrap(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;

    Dek d1 = kp.generate_dek();
    WrappedDek w1 = kp.wrap_dek(d1);               // wrapped under KEK v1

    std::uint64_t v2 = kp.rotate();
    if (v2 != 2) return 40;
    if (kp.active_kek_version() != 2) return 41;

    Dek d2 = kp.generate_dek();
    WrappedDek w2 = kp.wrap_dek(d2);               // wrapped under KEK v2
    if (w2.kek_version != 2) return 42;

    auto b1 = kp.unwrap_dek(w1);                   // v1 KEK retained
    if (!b1.has_value() || b1->material != d1.material) return 43;
    auto b2 = kp.unwrap_dek(w2);
    if (!b2.has_value() || b2->material != d2.material) return 44;
''', "rotate_old_still_unwrap")
    assert r.returncode == 0, r.stdout + r.stderr


def test_rotation_does_not_mutate_existing_wrapped_deks(tmp_path):
    # rotation is O(number of keys), not O(data): it mints a new KEK and
    # touches no already-wrapped DEK (and no ciphertext).
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;

    WrappedDek w = kp.wrap_dek(kp.generate_dek());
    const std::uint64_t ver_before = w.kek_version;
    const std::string bytes_before = w.bytes;

    kp.rotate();
    kp.rotate();

    if (w.kek_version != ver_before) return 50;
    if (w.bytes != bytes_before) return 51;
''', "rotate_no_mutation")
    assert r.returncode == 0, r.stdout + r.stderr


def test_unwrap_with_unknown_kek_version_returns_nullopt(tmp_path):
    # Rule 5: a distinct, observable failure -- not a throw, not a zeroed
    # key. Also the O.3 crypto-shred outcome, exercised early.
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;

    Dek d = kp.generate_dek();
    WrappedDek w = kp.wrap_dek(d);

    // fabricate a reference to a KEK version that never existed
    WrappedDek missing{999, w.bytes};
    if (kp.unwrap_dek(missing).has_value()) return 60;

    // and the deliberate-removal path
    kp.forget_kek_version(w.kek_version);
    if (kp.unwrap_dek(w).has_value()) return 61;
''', "unknown_version")
    assert r.returncode == 0, r.stdout + r.stderr


def test_used_polymorphically_through_base_reference(tmp_path):
    # how Track A's generated DAO will hold it: KeyProvider&, not the impl.
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;

    auto round_trip = [](KeyProvider& kp) {
        Dek d = kp.generate_dek();
        auto back = kp.unwrap_dek(kp.wrap_dek(d));
        return back.has_value() && back->material == d.material;
    };

    InMemoryKeyProvider impl;
    if (!round_trip(impl)) return 70;
''', "polymorphic")
    assert r.returncode == 0, r.stdout + r.stderr
