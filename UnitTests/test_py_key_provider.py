"""python-target / py-crypto-phi task 1: ``harpia_runtime.crypto.key_provider``
(``Crypto/runtime/python/key_provider.py``), the port of
``Crypto/runtime/harpia_key_provider.h``. Mirrors ``test_key_provider.py``,
``test_crypto_shred.py`` (in-memory half) and ``test_key_provider_audit.py``.

Pure Python: DEK wrap/unwrap/seal/open round trip; the wrapped DEK records
the active KEK version; rotate keeps old DEKs unwrappable and touches no
existing ``WrappedDek`` (O(keys)); a forgotten version / a shredded DEK
unwraps to ``None`` (per-DEK, KEK untouched, idempotent, no un-shred, a
later rotation doesn't resurrect it); exactly one audit record per op with
names only (no key bytes in any argument); the default sink is used when
none is passed; ``secure_zero`` / ``Dek.close`` zero the ``bytearray``;
the ``OP_*`` values equal the C++ ``kOp*`` strings.
g++: the XOR transform and ``shred_key`` are byte-identical to C++.
Image-gated: the copied module passes mypy --strict / ruff / sphinx -W.
"""
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

from Crypto.key_provider_common import (KEY_PROVIDER_RUNTIME_SRC,  # noqa: E402
                                        PY_KEY_PROVIDER_MODULE,
                                        PY_KEY_PROVIDER_RUNTIME_DEPS,
                                        PY_KEY_PROVIDER_RUNTIME_SRC)
from UnitTests._py_runtime_load import load_runtime  # noqa: E402

RUNTIMES = ((PY_KEY_PROVIDER_MODULE, PY_KEY_PROVIDER_RUNTIME_SRC),) + PY_KEY_PROVIDER_RUNTIME_DEPS
AUDIT = "harpia_runtime.compliance.audit_sink"


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    return load_runtime(tmp_path_factory.mktemp("py_kp"), RUNTIMES,
                        [PY_KEY_PROVIDER_MODULE, AUDIT])


@pytest.fixture(scope="module")
def kp(mods):
    return mods[PY_KEY_PROVIDER_MODULE]


def _sink(mods):
    class Recording(mods[AUDIT].AuditSink):
        def __init__(self):
            self.records = []

        def record(self, operation, subject, detail=""):
            self.records.append((operation, subject, detail))
    return Recording()


def test_op_names_match_cpp(kp):
    header = open(KEY_PROVIDER_RUNTIME_SRC).read()
    cpp = dict(re.findall(r'kOp(\w+)\s*=\s*"([^"]+)"', header))
    py = {n[3:].title(): getattr(kp, n) for n in dir(kp) if n.startswith("OP_")}
    assert py == cpp and len(py) == 5


def test_wrap_unwrap_seal_open_round_trip(kp):
    p = kp.InMemoryKeyProvider()
    dek = p.generate_dek()
    assert len(dek.material) == kp.KEY_LEN
    ct = dek.seal(b"patient-123")
    assert ct != b"patient-123"
    w = p.wrap_dek(dek)
    assert w.bytes != bytes(dek.material)
    back = p.unwrap_dek(w)
    assert back is not None and back.material == dek.material
    assert back.open(ct) == b"patient-123"


def test_wrapped_dek_records_active_version_and_rotation_is_o_keys(kp):
    p = kp.InMemoryKeyProvider()
    assert p.active_kek_version() == 1
    dek = p.generate_dek()
    w1 = p.wrap_dek(dek)
    snapshot = (w1.kek_version, w1.bytes)
    assert p.rotate() == 2 and p.active_kek_version() == 2
    assert (w1.kek_version, w1.bytes) == snapshot  # untouched
    old = p.unwrap_dek(w1)  # hold the Dek: its material is wiped when it goes
    assert old.material == dek.material  # old KEK retained
    w2 = p.wrap_dek(dek)
    assert w2.kek_version == 2 and w2.bytes != w1.bytes
    new = p.unwrap_dek(w2)
    assert new.material == dek.material
    with pytest.raises(AttributeError):
        w1.kek_version = 9  # frozen: rotation can't rewrite it in place


def test_unknown_version_returns_none(kp):
    p = kp.InMemoryKeyProvider()
    w = p.wrap_dek(p.generate_dek())
    p.forget_kek_version(1)
    assert p.unwrap_dek(w) is None
    assert p.unwrap_dek(kp.WrappedDek(42, b"x" * 32)) is None


def test_shred_is_per_dek_idempotent_and_irreversible(kp):
    p = kp.InMemoryKeyProvider()
    a, b = p.generate_dek(), p.generate_dek()
    wa, wb = p.wrap_dek(a), p.wrap_dek(b)
    p.shred_dek(wa)
    assert p.unwrap_dek(wa) is None
    other = p.unwrap_dek(wb)
    assert other.material == b.material  # other record intact
    assert p.active_kek_version() == 1  # KEK untouched
    p.shred_dek(wa)  # idempotent
    p.rotate()
    assert p.unwrap_dek(wa) is None  # rotation doesn't resurrect it
    assert not hasattr(p, "unshred_dek") and not hasattr(kp.KeyProvider, "unshred_dek")


def test_shred_key_format(kp):
    assert kp.shred_key(kp.WrappedDek(7, b"\x00ab")) == b"7:\x00ab"


def test_one_audit_record_per_op_names_only(kp, mods):
    sink = _sink(mods)
    p = kp.InMemoryKeyProvider(sink)
    dek = p.generate_dek()
    w = p.wrap_dek(dek)
    p.unwrap_dek(w)
    p.rotate()
    p.shred_dek(w)
    p.unwrap_dek(w)
    p.forget_kek_version(1)
    p.unwrap_dek(kp.WrappedDek(1, b"zz"))
    assert sink.records == [
        ("key_generate", "kek:1", ""),
        ("key_generate", "dek", ""),
        ("key_wrap", "kek:1", ""),
        ("key_unwrap", "kek:1", "ok"),
        ("key_rotate", "kek:2", ""),
        ("key_shred", "kek:1", ""),
        ("key_unwrap", "kek:1", "shredded"),
        ("key_unwrap", "kek:1", "unknown_version"),
    ]
    secrets_ = [bytes(dek.material), w.bytes]
    for record in sink.records:
        for arg in record:
            assert isinstance(arg, str)
            for s in secrets_:
                assert s.hex() not in arg and s.decode("latin-1") not in arg


def test_default_sink_when_none_passed(kp, mods):
    p = kp.InMemoryKeyProvider()
    assert p._audit is mods[AUDIT].default_audit_sink()


def test_zeroization(kp):
    buf = bytearray(b"secret-key")
    kp.secure_zero(buf)
    assert buf == bytearray()
    dek = kp.Dek(b"\x01" * 32)
    material = dek.material
    with dek:
        assert material == bytearray(b"\x01" * 32)
    assert material == bytearray()  # same object, wiped in place
    # a temporary Dek's material is wiped as soon as the Dek is collected
    p0 = kp.InMemoryKeyProvider()
    leaked = p0.unwrap_dek(p0.wrap_dek(p0.generate_dek())).material
    assert leaked == bytearray()
    p = kp.InMemoryKeyProvider()
    kek = p._keks[1]
    p.forget_kek_version(1)
    assert kek == bytearray()


def test_used_through_the_abc(kp):
    def round_trip(provider):
        dek = provider.generate_dek()
        back = provider.unwrap_dek(provider.wrap_dek(dek))
        return back.material == dek.material
    assert isinstance(kp.InMemoryKeyProvider(), kp.KeyProvider)
    assert round_trip(kp.InMemoryKeyProvider())
    with pytest.raises(TypeError):
        kp.KeyProvider()


_CPP = r'''
#include <cstdio>
#include <string>
#include "harpia_key_provider.h"
static std::string unhex(const char* h) {
    std::string out;
    for (const char* p = h; p[0] && p[1]; p += 2) {
        unsigned v; std::sscanf(p, "%2x", &v); out += static_cast<char>(v);
    }
    return out;
}
static void hex(const std::string& s) {
    for (unsigned char c : s) std::printf("%02x", c);
    std::printf("\n");
}
int main(int, char** argv) {
    harpia::crypto::Dek dek(unhex(argv[1]));
    hex(dek.seal(unhex(argv[2])));
    hex(harpia::crypto::Dek::xor_with(unhex(argv[2]), ""));
    hex(harpia::crypto::shred_key(harpia::crypto::WrappedDek{7, unhex(argv[1])}));
}
'''


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_transform_and_shred_key_match_cpp(kp, tmp_path):
    src = tmp_path / "x.cpp"
    src.write_text(_CPP)
    exe = tmp_path / "x"
    c = subprocess.run(["g++", "-std=c++17", "-I", os.path.join(REPO_ROOT, "Crypto", "runtime"),
                        "-I", os.path.join(REPO_ROOT, "Compliance", "runtime"),
                        str(src), "-o", str(exe)], capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    key, pt = bytes(range(1, 33)), "v\"<&'>\\\n\té-".encode() * 5
    out = subprocess.run([str(exe), key.hex(), pt.hex()], capture_output=True, text=True,
                         check=True).stdout.split()
    assert bytes.fromhex(out[0]) == kp.Dek(key).seal(pt)
    assert bytes.fromhex(out[1]) == kp.xor_with(pt, b"") == pt
    assert bytes.fromhex(out[2]) == kp.shred_key(kp.WrappedDek(7, key))


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
    assert PY_KEY_PROVIDER_MODULE in open(os.path.join(py_root, "docs", "api.rst")).read()
    for cmd in (["mypy", "--no-incremental"], ["ruff", "check", "--no-cache", "."],
                ["sphinx-build", "-q", "-W", "-E", "docs", str(tmp_path / "html")]):
        r = subprocess.run(cmd, cwd=py_root, capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, " ".join(cmd) + "\n" + r.stdout + r.stderr
