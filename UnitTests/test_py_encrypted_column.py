"""python-target / py-crypto-phi task 3: ``harpia_runtime.crypto.encrypted_column``
(``Crypto/runtime/python/encrypted_column.py``), the port of
``harpia_encrypted_column.h``.

Pure Python: round trip (ASCII, UTF-8, empty); the ``enc:v1:`` frame layout
(big-endian u64 version, u32 wrapped length, wrapped DEK, ciphertext;
lowercase hex); each call uses a fresh DEK; numeric phi (``strtoll`` /
``strtod`` prefix parsing, int64 saturation, 32-bit wrap); a value without
the marker passes through; tampered / truncated / non-hex / unknown-key /
shredded / non-UTF-8 values give ``""`` / ``0`` and never raise; a rotation
keeps old values readable; ``default_key_provider()`` is one in-memory
instance.
g++: over one shared ``LocalKeyProvider`` store, a value encrypted by C++
decrypts in Python and the reverse (text, int, double), and C++ and Python
agree on every unrecoverable input.
Image-gated: the copied module passes mypy --strict / ruff / sphinx -W.
"""
import os
import shutil
import struct
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Crypto.key_provider_common import (  # noqa: E402
    PY_ENCRYPTED_COLUMN_MODULE, PY_ENCRYPTED_COLUMN_RUNTIME_DEPS,
    PY_ENCRYPTED_COLUMN_RUNTIME_SRC, PY_KEY_PROVIDER_LOCAL_MODULE,
    PY_KEY_PROVIDER_LOCAL_RUNTIME_SRC, PY_KEY_PROVIDER_MODULE)
from UnitTests._py_runtime_load import load_runtime  # noqa: E402

RUNTIMES = ((PY_ENCRYPTED_COLUMN_MODULE, PY_ENCRYPTED_COLUMN_RUNTIME_SRC),
            (PY_KEY_PROVIDER_LOCAL_MODULE, PY_KEY_PROVIDER_LOCAL_RUNTIME_SRC)) \
    + PY_ENCRYPTED_COLUMN_RUNTIME_DEPS


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    return load_runtime(tmp_path_factory.mktemp("py_enc"), RUNTIMES,
                        [PY_ENCRYPTED_COLUMN_MODULE, PY_KEY_PROVIDER_MODULE,
                         PY_KEY_PROVIDER_LOCAL_MODULE])


@pytest.fixture(scope="module")
def ec(mods):
    return mods[PY_ENCRYPTED_COLUMN_MODULE]


@pytest.fixture(scope="module")
def kp(mods):
    return mods[PY_KEY_PROVIDER_MODULE]


@pytest.mark.parametrize("text", ["patient-123", "", "José ünïcödé ✓", "a" * 1000])
def test_round_trip(ec, kp, text):
    p = kp.InMemoryKeyProvider()
    stored = ec.encrypt_field(p, text)
    assert stored.startswith("enc:v1:") and (text == "" or text not in stored)
    assert ec.decrypt_field(p, stored) == text


def test_frame_layout_and_fresh_dek_per_value(ec, kp):
    p = kp.InMemoryKeyProvider()
    p.rotate()
    stored = ec.encrypt_field(p, "abc")
    body = stored[len("enc:v1:"):]
    assert body == body.lower()
    frame = bytes.fromhex(body)
    version, n = struct.unpack(">QI", frame[:12])
    assert version == 2 and n == 32 and len(frame) == 12 + 32 + 3
    assert ec.encrypt_field(p, "abc") != stored  # a fresh DEK each time


def test_numeric(ec, kp):
    p = kp.InMemoryKeyProvider()
    enc = lambda v: ec.encrypt_field(p, v)  # noqa: E731
    assert ec.decrypt_field_int(p, enc("42")) == 42
    assert ec.decrypt_field_int(p, enc("  -17xyz")) == -17
    assert ec.decrypt_field_int(p, enc("4294967297")) == 1  # 32-bit wrap
    assert ec.decrypt_field_ll(p, enc("99999999999999999999")) == (1 << 63) - 1
    assert ec.decrypt_field_ll(p, enc("-" + "9" * 5000)) == -(1 << 63)
    assert ec.decrypt_field_float(p, enc("98.600000")) == 98.6
    assert ec.decrypt_field_float(p, enc("1e3abc")) == 1000.0
    assert ec.decrypt_field_float(p, enc("abc")) == 0.0
    assert ec.decrypt_field_int(p, enc("")) == 0


def test_unrecoverable_never_raises(ec, kp):
    p = kp.InMemoryKeyProvider()
    good = ec.encrypt_field(p, "secret")
    assert ec.decrypt_field(p, "plain legacy") == "plain legacy"
    for bad in ["enc:v1:", "enc:v1:zz", "enc:v1:abc", "enc:v1:00 11",
                good[:30], "enc:v1:" + "00" * 11,
                "enc:v1:" + (struct.pack(">QI", 1, 999) + b"x").hex()]:
        assert ec.decrypt_field(p, bad) == "", bad
        assert ec.decrypt_field_int(p, bad) == 0 and ec.decrypt_field_float(p, bad) == 0.0
    assert ec.decrypt_field(p, good[:-2]) == "secre"  # a shorter ciphertext is still a frame
    assert ec.decrypt_field(kp.InMemoryKeyProvider(), good) != "secret"  # other KEK
    frame = bytes.fromhex(good[len("enc:v1:"):])
    w = kp.WrappedDek(*struct.unpack(">Q", frame[:8]), frame[12:44])
    p.shred_dek(w)
    assert ec.decrypt_field(p, good) == ""
    q = kp.InMemoryKeyProvider()
    v = ec.encrypt_field(q, "x")
    q.forget_kek_version(1)
    assert ec.decrypt_field(q, v) == ""
    # a ciphertext that opens to invalid UTF-8
    r = kp.InMemoryKeyProvider()
    f = bytearray.fromhex(ec.encrypt_field(r, "é")[len("enc:v1:"):])
    f[-1] ^= 0xFF
    assert ec.decrypt_field(r, "enc:v1:" + f.hex()) == ""


def test_rotation_keeps_old_values(ec, kp):
    p = kp.InMemoryKeyProvider()
    old = ec.encrypt_field(p, "before")
    p.rotate()
    assert ec.decrypt_field(p, old) == "before"
    assert ec.decrypt_field(p, ec.encrypt_field(p, "after")) == "after"


def test_default_key_provider(ec, kp):
    a = ec.default_key_provider()
    assert a is ec.default_key_provider() and isinstance(a, kp.InMemoryKeyProvider)
    assert ec.decrypt_field(a, ec.encrypt_field(a, "z")) == "z"


_CPP = r'''
#include <cstdio>
#include <string>
#include "harpia_encrypted_column.h"
#include "harpia_key_provider_local.h"
using namespace harpia::crypto;
int main(int, char** argv) {
    LocalKeyProvider p(LocalKeyProviderConfig{argv[1], false, false});
    std::string mode = argv[2], arg = argv[3];
    if (mode == "enc") std::printf("%s\n", encrypt_field(p, arg).c_str());
    else if (mode == "dec") std::printf("[%s]\n", decrypt_field(p, arg).c_str());
    else if (mode == "int") std::printf("%d\n", decrypt_field_int(p, arg));
    else if (mode == "dbl") std::printf("%.17g\n", decrypt_field_double(p, arg));
    else if (mode == "encd") std::printf("%s\n", encrypt_field(p, std::to_string(std::stod(arg))).c_str());
    return 0;
}
'''


@pytest.fixture(scope="module")
def cpp_col(tmp_path_factory):
    if shutil.which("g++") is None:
        pytest.skip("needs g++")
    d = tmp_path_factory.mktemp("cpp_enc")
    (d / "x.cpp").write_text(_CPP)
    exe = d / "x"
    c = subprocess.run(["g++", "-std=c++17", "-I", os.path.join(REPO_ROOT, "Crypto", "runtime"),
                        "-I", os.path.join(REPO_ROOT, "Compliance", "runtime"),
                        str(d / "x.cpp"), "-o", str(exe)],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    return str(exe)


def _cpp(exe, store, mode, arg):
    return subprocess.run([exe, str(store), mode, arg], capture_output=True, text=True,
                          check=True, timeout=60).stdout.rstrip("\n")


def _local(mods, store):
    loc = mods[PY_KEY_PROVIDER_LOCAL_MODULE]
    return loc.LocalKeyProvider(loc.LocalKeyProviderConfig(str(store)))


@pytest.mark.parametrize("text", ["patient-123", "José ✓", "line\nbreak"])
def test_cross_language_text(text, ec, mods, cpp_col, tmp_path):
    store = tmp_path / "keks"
    from_cpp = _cpp(cpp_col, store, "enc", text)
    p = _local(mods, store)
    assert ec.decrypt_field(p, from_cpp) == text
    assert _cpp(cpp_col, store, "dec", ec.encrypt_field(p, text)) == "[{}]".format(text)


def test_cross_language_numeric(ec, mods, cpp_col, tmp_path):
    store = tmp_path / "keks"
    p = _local(mods, store)
    assert _cpp(cpp_col, store, "int", ec.encrypt_field(p, "-12345")) == "-12345"
    assert float(_cpp(cpp_col, store, "dbl", ec.encrypt_field(p, "98.600000"))) == 98.6
    assert ec.decrypt_field_float(p, _cpp(cpp_col, store, "encd", "36.6")) == 36.6
    assert ec.decrypt_field_int(p, _cpp(cpp_col, store, "enc", "4294967297")) == \
        int(_cpp(cpp_col, store, "int", _cpp(cpp_col, store, "enc", "4294967297")))


@pytest.mark.parametrize("bad", ["enc:v1:", "enc:v1:zz", "enc:v1:abc", "enc:v1:" + "00" * 11,
                                 "enc:v1:" + "00" * 12, "plain legacy"])
def test_cross_language_unrecoverable_agree(bad, ec, mods, cpp_col, tmp_path):
    store = tmp_path / "keks"
    p = _local(mods, store)
    assert "[{}]".format(ec.decrypt_field(p, bad)) == _cpp(cpp_col, store, "dec", bad)


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in
        ("mypy", "ruff", "sphinx-build", "protoc", "grpc_python_plugin")),
    reason="Python quality-gate toolchain not installed (runs in the harpia-build image)")
def test_copied_module_passes_the_gate(tmp_path):
    from PyAdapter.PyDocsAdapter import PyDocsAdapter
    from PyAdapter.runtime_copy import copy_runtime_module
    from UnitTests._java_gradle_helpers import generate
    out = generate(tmp_path, lang="python")
    for module, src in RUNTIMES:
        copy_runtime_module(out, src, module)
    PyDocsAdapter(messages=[], dest=out).Process()
    py_root = os.path.join(out, "python")
    for cmd in (["mypy", "--no-incremental"], ["ruff", "check", "--no-cache", "."],
                ["sphinx-build", "-q", "-W", "-E", "docs", str(tmp_path / "html")]):
        r = subprocess.run(cmd, cwd=py_root, capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, " ".join(cmd) + "\n" + r.stdout + r.stderr
