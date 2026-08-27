"""Tests for Track O, Session O.3 -- crypto-shredding.

shred_dek(w) permanently and irreversibly discards the DEK a WrappedDek
refers to: afterwards unwrap_dek(w) returns nullopt even though the KEK is
intact, so exactly that one record's ciphertext becomes unrecoverable
without ever locating or rewriting the ciphertext (right-to-erasure --
destroy the key, not the data). Per-DEK: shredding one record does not
touch any other.

Exercised against BOTH providers (O.3 works against either): O.1's
InMemoryKeyProvider and O.2's file-persisted LocalKeyProvider (whose shred
must also survive a restart). Same compile-and-run C++ pattern as
test_key_provider.py / test_local_key_provider.py. Skipped when g++ is
absent.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ not available")


def _compile_and_run(tmp_path, body, name, extra_top=""):
    src = tmp_path / "{}.cpp".format(name)
    src.write_text(
        '#include "Crypto/runtime/harpia_key_provider_local.h"\n'
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


def _store(tmp_path):
    return str(tmp_path / "keks.store").replace("\\", "/")


# ---- InMemoryKeyProvider (O.1) --------------------------------------------

def test_inmemory_shred_makes_only_that_record_unrecoverable(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;

    Dek d = kp.generate_dek();
    WrappedDek w = kp.wrap_dek(d);
    const std::string sealed = d.seal("record-A phi");

    // before shred: fully recoverable
    auto pre = kp.unwrap_dek(w);
    if (!pre.has_value() || pre->open(sealed) != "record-A phi") return 10;

    const std::string w_bytes_before = w.bytes;
    kp.shred_dek(w);

    // after shred: gone -- and the KEK was NOT touched
    if (kp.unwrap_dek(w).has_value()) return 11;
    if (kp.active_kek_version() != 1) return 12;
    if (w.bytes != w_bytes_before) return 13;          // caller's WrappedDek intact

    // a different record's DEK is completely unaffected (per-DEK shred)
    Dek d2 = kp.generate_dek();
    WrappedDek w2 = kp.wrap_dek(d2);
    auto other = kp.unwrap_dek(w2);
    if (!other.has_value() || other->material != d2.material) return 14;
''', "inmem_shred")
    assert r.returncode == 0, r.stdout + r.stderr


def test_inmemory_shred_is_idempotent_and_irreversible(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    InMemoryKeyProvider kp;
    Dek d = kp.generate_dek();
    WrappedDek w = kp.wrap_dek(d);

    kp.shred_dek(w);
    kp.shred_dek(w);                                   // idempotent, no throw
    if (kp.unwrap_dek(w).has_value()) return 20;

    // even a KEK rotation afterwards does not resurrect it
    kp.rotate();
    if (kp.unwrap_dek(w).has_value()) return 21;
''', "inmem_shred_idem",
        extra_top='''
#include <type_traits>
#include <utility>
template <class T, class = void> struct has_unshred : std::false_type {};
template <class T>
struct has_unshred<T, std::void_t<decltype(std::declval<T&>().unshred_dek(
    std::declval<harpia::crypto::WrappedDek>()))>> : std::true_type {};
static_assert(!has_unshred<harpia::crypto::InMemoryKeyProvider>::value,
              "crypto-shred must be irreversible -- no un-shred API");
static_assert(!has_unshred<harpia::crypto::LocalKeyProvider>::value,
              "crypto-shred must be irreversible -- no un-shred API");
''')
    assert r.returncode == 0, r.stdout + r.stderr


# ---- LocalKeyProvider (O.2) ---------------------------------------------

def test_local_shred_survives_restart(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";

    WrappedDek w;
    std::string mat;
    {
        LocalKeyProvider a(cfg);
        Dek d = a.generate_dek();
        mat = d.material;
        w = a.wrap_dek(d);
        auto pre = a.unwrap_dek(w);
        if (!pre.has_value() || pre->material != mat) return 30;
        a.shred_dek(w);
        if (a.unwrap_dek(w).has_value()) return 31;
    }
    // brand-new instance at the same path -- the shred must still hold
    {
        LocalKeyProvider b(cfg);
        if (b.unwrap_dek(w).has_value()) return 32;
        if (b.active_kek_version() != 1) return 33;    // KEK store untouched
        Dek d2 = b.generate_dek();                     // fresh records still work
        auto ok = b.unwrap_dek(b.wrap_dek(d2));
        if (!ok.has_value()) return 34;
    }
''' % _store(tmp_path), "local_shred_restart")
    assert r.returncode == 0, r.stdout + r.stderr


def test_local_shred_is_per_record(tmp_path):
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    LocalKeyProvider kp(cfg);

    Dek d1 = kp.generate_dek(); WrappedDek w1 = kp.wrap_dek(d1);
    Dek d2 = kp.generate_dek(); WrappedDek w2 = kp.wrap_dek(d2);

    kp.shred_dek(w1);
    if (kp.unwrap_dek(w1).has_value()) return 40;
    auto r2 = kp.unwrap_dek(w2);
    if (!r2.has_value() || r2->material != d2.material) return 41;
''' % _store(tmp_path), "local_shred_per_record")
    assert r.returncode == 0, r.stdout + r.stderr


def test_shred_sidecar_does_not_touch_the_kek_store(tmp_path):
    # the guarantee "without touching or rewriting the ciphertext" extends to
    # the KEK store: a shred goes to <path>.shred, the KEK file is byte-stable.
    store = _store(tmp_path)
    r = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    LocalKeyProvider kp(cfg);
    Dek d = kp.generate_dek();
    kp.shred_dek(kp.wrap_dek(d));
''' % store, "local_shred_sidecar")
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(store), "KEK store missing"
    assert os.path.isfile(store + ".shred"), "shred sidecar not written"
    kek_before = open(store).read()
    # run again against the same store, shredding another DEK
    r2 = _compile_and_run(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    LocalKeyProvider kp(cfg);
    Dek d = kp.generate_dek();
    kp.shred_dek(kp.wrap_dek(d));
''' % store, "local_shred_sidecar2")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert open(store).read() == kek_before, "KEK store was rewritten by a shred"
    assert len(open(store + ".shred").read().splitlines()) == 2, \
        "shred sidecar should have appended, not replaced"
