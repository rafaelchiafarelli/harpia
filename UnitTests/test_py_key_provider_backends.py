"""python-target / py-crypto-phi task 2: ``harpia_runtime.crypto.key_provider_local``
and ``harpia_runtime.crypto.key_provider_kms`` (``Crypto/runtime/python/``),
ports of ``harpia_key_provider_local.h`` / ``harpia_key_provider_kms.h``.
Mirrors ``test_local_key_provider.py``, ``test_kms_key_provider.py`` and the
local half of ``test_crypto_shred.py``.

Pure Python: both satisfy the KeyProvider contract; KEKs (and rotations)
survive a restart at the same path, in the ``<version> <hex>`` store format;
the PHI-at-scale gate refuses without acknowledgment, accepts with it, and
doesn't bite when not at scale; the env helper; shred appends to
``<path>.shred`` (once per DEK), never rewrites the store, survives a
restart, is per record; KMS version retirement and per-DEK shred → ``None``;
audit records for every op; one round-trip function runs unchanged on the
in-memory, local and KMS providers.
g++: a store + wrapped DEK written by the C++ ``LocalKeyProvider`` unwraps in
Python, Python shreds it and C++ then refuses it -- and the reverse.
Image-gated: both copied modules pass mypy --strict / ruff / sphinx -W.
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

from Crypto.key_provider_common import (  # noqa: E402
    PY_KEY_PROVIDER_KMS_MODULE, PY_KEY_PROVIDER_KMS_RUNTIME_DEPS,
    PY_KEY_PROVIDER_KMS_RUNTIME_SRC, PY_KEY_PROVIDER_LOCAL_MODULE,
    PY_KEY_PROVIDER_LOCAL_RUNTIME_DEPS, PY_KEY_PROVIDER_LOCAL_RUNTIME_SRC,
    PY_KEY_PROVIDER_MODULE)
from UnitTests._py_runtime_load import load_runtime  # noqa: E402

RUNTIMES = ((PY_KEY_PROVIDER_LOCAL_MODULE, PY_KEY_PROVIDER_LOCAL_RUNTIME_SRC),
            (PY_KEY_PROVIDER_KMS_MODULE, PY_KEY_PROVIDER_KMS_RUNTIME_SRC)) \
    + PY_KEY_PROVIDER_LOCAL_RUNTIME_DEPS
assert set(PY_KEY_PROVIDER_KMS_RUNTIME_DEPS) <= set(RUNTIMES)
AUDIT = "harpia_runtime.compliance.audit_sink"


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    return load_runtime(tmp_path_factory.mktemp("py_kp_backends"), RUNTIMES,
                        [PY_KEY_PROVIDER_MODULE, PY_KEY_PROVIDER_LOCAL_MODULE,
                         PY_KEY_PROVIDER_KMS_MODULE, AUDIT])


@pytest.fixture(scope="module")
def kp(mods):
    return mods[PY_KEY_PROVIDER_MODULE]


@pytest.fixture(scope="module")
def local(mods):
    return mods[PY_KEY_PROVIDER_LOCAL_MODULE]


@pytest.fixture(scope="module")
def kms(mods):
    return mods[PY_KEY_PROVIDER_KMS_MODULE]


def _sink(mods):
    class Recording(mods[AUDIT].AuditSink):
        def __init__(self):
            self.records = []

        def record(self, operation, subject, detail=""):
            self.records.append((operation, subject, detail))
    return Recording()


def _local(local, path, **kw):
    return local.LocalKeyProvider(local.LocalKeyProviderConfig(str(path), **kw))


def _round_trip(provider):
    """The same KeyProvider code for every backend (no interface change)."""
    dek = provider.generate_dek()
    ct = dek.seal(b"value")
    w = provider.wrap_dek(dek)
    back = provider.unwrap_dek(w)
    return back is not None and back.material == dek.material and back.open(ct) == b"value"


def test_backends_interchangeable(kp, local, kms, tmp_path):
    providers = [kp.InMemoryKeyProvider(), _local(local, tmp_path / "s"),
                 kms.KmsKeyProvider(kms.MockKms())]
    for p in providers:
        assert isinstance(p, kp.KeyProvider) and _round_trip(p)


def test_store_format_and_restart(local, tmp_path):
    path = tmp_path / "keks.txt"
    a = _local(local, path)
    dek = a.generate_dek()
    w = a.wrap_dek(dek)
    line = path.read_text()
    v, hexkey = line.split()
    assert line.endswith("\n") and v == "1" and len(hexkey) == 64 and hexkey == hexkey.lower()
    assert a.rotate() == 2
    assert [ln.split()[0] for ln in path.read_text().splitlines()] == ["1", "2"]
    b = _local(local, path)  # "restart"
    assert b.active_kek_version() == 2
    back = b.unwrap_dek(w)
    assert back is not None and back.material == dek.material


def test_gate(local, tmp_path, monkeypatch):
    with pytest.raises(local.LocalKeyProviderRefused):
        _local(local, tmp_path / "a", phi_at_scale=True)
    assert not (tmp_path / "a").exists()  # refused before touching the store
    assert _round_trip(_local(local, tmp_path / "b", phi_at_scale=True, acknowledged=True))
    assert _round_trip(_local(local, tmp_path / "c", phi_at_scale=False))
    for value, want in [("1", True), ("TRUE", True), ("Yes", True), ("0", False),
                        ("no", False), ("", False)]:
        monkeypatch.setenv(local.ACK_ENV, value)
        assert local.local_key_provider_acknowledged() is want
    monkeypatch.delenv(local.ACK_ENV)
    assert local.local_key_provider_acknowledged() is False


def test_local_shred_sidecar(local, tmp_path):
    path = tmp_path / "keks.txt"
    p = _local(local, path)
    a, b = p.generate_dek(), p.generate_dek()
    wa, wb = p.wrap_dek(a), p.wrap_dek(b)
    store_before = path.read_bytes()
    p.shred_dek(wa)
    p.shred_dek(wa)  # idempotent: one sidecar line
    assert path.read_bytes() == store_before  # store untouched
    assert (tmp_path / "keks.txt.shred").read_text() == "1 {}\n".format(wa.bytes.hex())
    assert p.unwrap_dek(wa) is None
    q = _local(local, path)  # restart
    assert q.unwrap_dek(wa) is None
    other = q.unwrap_dek(wb)
    assert other is not None and other.material == b.material  # per record



@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_local_store_and_sidecar_are_0600(local, tmp_path):
    """cpp-key-store-permissions-DEFECT (Python mirror): store + sidecar are
    owner-only whatever the umask, also after a rotate rewrite."""
    old = os.umask(0o022)
    try:
        path = tmp_path / "keks.txt"
        p = _local(local, path)
        p.shred_dek(p.wrap_dek(p.generate_dek()))
        p.rotate()
    finally:
        os.umask(old)
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)
    assert oct((tmp_path / "keks.txt.shred").stat().st_mode & 0o777) == oct(0o600)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
@pytest.mark.parametrize("loose", ["store", "shred"])
def test_local_loose_store_is_refused(local, tmp_path, loose):
    """A loose store / sidecar raises LocalKeyStoreInsecure (path + mode in
    the message), before anything is read or rewritten -- as C++."""
    path = tmp_path / "keks.txt"
    p = _local(local, path)
    p.shred_dek(p.wrap_dek(p.generate_dek()))
    target = path if loose == "store" else tmp_path / "keks.txt.shred"
    os.chmod(target, 0o640)
    before = path.read_bytes()
    with pytest.raises(local.LocalKeyStoreInsecure) as e:
        _local(local, path)
    assert str(target) in str(e.value) and "0640" in str(e.value)
    assert path.read_bytes() == before and target.stat().st_mode & 0o777 == 0o640

def test_local_audit(local, mods, tmp_path):
    sink = _sink(mods)
    path = tmp_path / "s"
    p = local.LocalKeyProvider(local.LocalKeyProviderConfig(str(path)), sink)
    w = p.wrap_dek(p.generate_dek())
    p.rotate()
    p.shred_dek(w)
    p.unwrap_dek(w)
    assert [r[0] for r in sink.records] == ["key_generate", "key_generate", "key_wrap",
                                           "key_rotate", "key_shred", "key_unwrap"]
    sink2 = _sink(mods)
    local.LocalKeyProvider(local.LocalKeyProviderConfig(str(path)), sink2)
    assert sink2.records == []  # loading an existing store mints no KEK


def test_kms_shred_retirement_and_audit(kms, mods):
    sink = _sink(mods)
    mock = kms.MockKms()
    p = kms.KmsKeyProvider(mock, sink)
    a, b = p.generate_dek(), p.generate_dek()
    wa, wb = p.wrap_dek(a), p.wrap_dek(b)
    p.shred_dek(wa)
    assert p.unwrap_dek(wa) is None
    assert p.rotate() == 2 and p.active_kek_version() == 2
    mock.forget_version(1)
    assert p.unwrap_dek(wb) is None
    assert sink.records == [
        ("key_generate", "dek", ""), ("key_generate", "dek", ""),
        ("key_wrap", "kek:1", ""), ("key_wrap", "kek:1", ""),
        ("key_shred", "kek:1", ""), ("key_unwrap", "kek:1", "shredded"),
        ("key_rotate", "kek:2", ""), ("key_unwrap", "kek:1", "unknown_version"),
    ]
    with pytest.raises(TypeError):
        kms.KmsClient()


_CPP = r'''
#include <cstdio>
#include <string>
#include "harpia_key_provider_local.h"
using namespace harpia::crypto;
static std::string unhex(const std::string& h) {
    std::string out;
    for (size_t i = 0; i + 1 < h.size(); i += 2)
        out += static_cast<char>(std::stoi(h.substr(i, 2), nullptr, 16));
    return out;
}
static std::string hex(const std::string& s) {
    std::string out; char b[3];
    for (unsigned char c : s) { std::snprintf(b, 3, "%02x", c); out += b; }
    return out;
}
int main(int argc, char** argv) {
    std::string mode = argv[1];
    LocalKeyProvider p(LocalKeyProviderConfig{argv[2], false, false});
    if (mode == "wrap") {
        Dek dek = p.generate_dek();
        WrappedDek w = p.wrap_dek(dek);
        std::printf("%llu %s %s\n", (unsigned long long)w.kek_version,
                    hex(w.bytes).c_str(), hex(dek.material).c_str());
        return 0;
    }
    WrappedDek w{std::stoull(argv[3]), unhex(argv[4])};
    if (mode == "shred") { p.shred_dek(w); return 0; }
    auto d = p.unwrap_dek(w);
    std::printf("%s\n", d ? hex(d->material).c_str() : "NONE");
    return 0;
}
'''


@pytest.fixture(scope="module")
def cpp_local(tmp_path_factory):
    if shutil.which("g++") is None:
        pytest.skip("needs g++")
    d = tmp_path_factory.mktemp("cpp_local")
    (d / "x.cpp").write_text(_CPP)
    exe = d / "x"
    c = subprocess.run(["g++", "-std=c++17", "-I", os.path.join(REPO_ROOT, "Crypto", "runtime"),
                        "-I", os.path.join(REPO_ROOT, "Compliance", "runtime"),
                        str(d / "x.cpp"), "-o", str(exe)],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    return str(exe)


def _run(exe, *args):
    return subprocess.run([exe, *map(str, args)], capture_output=True, text=True,
                          check=True, timeout=60).stdout.split()


def test_cpp_store_unwraps_in_python_and_python_shred_binds_cpp(local, kp, cpp_local, tmp_path):
    path = tmp_path / "shared.keks"
    v, wrapped, dek_hex = _run(cpp_local, "wrap", path)
    p = _local(local, path)
    w = kp.WrappedDek(int(v), bytes.fromhex(wrapped))
    back = p.unwrap_dek(w)
    assert back is not None and back.material.hex() == dek_hex
    p.shred_dek(w)
    assert _run(cpp_local, "unwrap", path, v, wrapped) == ["NONE"]


def test_python_store_unwraps_in_cpp_and_cpp_shred_binds_python(local, cpp_local, tmp_path):
    path = tmp_path / "shared.keks"
    p = _local(local, path)
    p.rotate()  # a two-KEK store, wrapped under v2
    dek = p.generate_dek()
    w = p.wrap_dek(dek)
    assert _run(cpp_local, "unwrap", path, w.kek_version, w.bytes.hex()) == [dek.material.hex()]
    _run(cpp_local, "shred", path, w.kek_version, w.bytes.hex())
    assert _local(local, path).unwrap_dek(w) is None
    if os.name != "nt":  # either language's files load in the other: both 0600
        for f in (path, tmp_path / "shared.keks.shred"):
            assert f.stat().st_mode & 0o777 == 0o600


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in
        ("mypy", "ruff", "sphinx-build", "protoc", "grpc_python_plugin")),
    reason="Python quality-gate toolchain not installed (runs in the harpia-build image)")
def test_copied_modules_pass_the_gate(tmp_path):
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
