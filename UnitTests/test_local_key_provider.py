"""Tests for Track O, Session O.2 -- the default local KeyProvider + the
fail-safe acknowledgment gate (Crypto/runtime/harpia_key_provider_local.h).

Hand-written C++, same compile-and-run pattern as test_key_provider.py
(O.1) / test_audit_sink.py / test_delivery_runtime.py. Skipped when g++ is
absent.

Covers O.2's stated bar:
  - Unit: LocalKeyProvider satisfies O.1's KeyProvider contract (the same
    wrap/unwrap/rotate/unknown-version assertions, unmodified).
  - Unit: a PHI-at-scale profile WITHOUT acknowledgment refuses to proceed
    (throws LocalKeyProviderRefused); WITH acknowledgment it proceeds.
Plus what makes it "local storage": KEK material persists across provider
instances pointed at the same file, rotation included.
"""
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

from Crypto.key_provider_common import (  # noqa: E402
    KEY_PROVIDER_LOCAL_RUNTIME_SRC, KEY_PROVIDER_LOCAL_RUNTIME_DEPS)

pytestmark = pytest.mark.skipif(
    shutil.which("g++") is None, reason="g++ not available")


def _compile(tmp_path, body, name, extra_top=""):
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
    return binpath


def _run(binpath, env=None):
    full = dict(os.environ)
    if env:
        full.update(env)
    return subprocess.run([str(binpath)], capture_output=True, text=True,
                          env=full)


def _store(tmp_path):
    # forward slashes only; safe to drop straight into a C++ string literal
    return str(tmp_path / "keks.store").replace("\\", "/")


def test_common_module_paths_resolve():
    assert os.path.isfile(KEY_PROVIDER_LOCAL_RUNTIME_SRC)
    assert KEY_PROVIDER_LOCAL_RUNTIME_SRC.endswith("harpia_key_provider_local.h")
    # the O.1 header is named as a co-copy dependency
    names = [n for n, _ in KEY_PROVIDER_LOCAL_RUNTIME_DEPS]
    assert "harpia_key_provider.h" in names
    for _, dep_src in KEY_PROVIDER_LOCAL_RUNTIME_DEPS:
        assert os.path.isfile(dep_src)


def test_local_provider_satisfies_the_keyprovider_contract(tmp_path):
    b = _compile(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    LocalKeyProvider kp(cfg);

    Dek d = kp.generate_dek();
    if (d.material.empty()) return 10;

    WrappedDek w = kp.wrap_dek(d);
    if (w.bytes == d.material) return 11;
    auto back = kp.unwrap_dek(w);
    if (!back.has_value() || back->material != d.material) return 12;

    const std::string pt = "heart_rate=72";
    std::string sealed = d.seal(pt);
    if (sealed == pt) return 13;
    if (d.open(sealed) != pt) return 14;

    std::uint64_t v2 = kp.rotate();
    if (v2 != 2 || kp.active_kek_version() != 2) return 15;
    auto b1 = kp.unwrap_dek(w);                 // retained KEK v1
    if (!b1.has_value() || b1->material != d.material) return 16;

    WrappedDek missing{999, w.bytes};
    if (kp.unwrap_dek(missing).has_value()) return 17;
''' % _store(tmp_path), "local_contract")
    r = _run(b)
    assert r.returncode == 0, r.stdout + r.stderr


def test_keks_persist_across_instances_at_the_same_path(tmp_path):
    b = _compile(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";

    WrappedDek w;
    std::string material;
    {
        LocalKeyProvider a(cfg);
        Dek d = a.generate_dek();
        material = d.material;
        w = a.wrap_dek(d);
    }
    LocalKeyProvider fresh(cfg);                // new instance, same file
    auto back = fresh.unwrap_dek(w);
    if (!back.has_value() || back->material != material) return 20;
''' % _store(tmp_path), "local_persist")
    r = _run(b)
    assert r.returncode == 0, r.stdout + r.stderr


def test_rotation_is_persisted(tmp_path):
    b = _compile(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";

    WrappedDek w1;
    std::string m1;
    {
        LocalKeyProvider a(cfg);
        Dek d = a.generate_dek();
        m1 = d.material;
        w1 = a.wrap_dek(d);                     // wrapped under KEK v1
        if (a.rotate() != 2) return 30;
    }
    {
        LocalKeyProvider b(cfg);
        if (b.active_kek_version() != 2) return 31;   // rotation survived
        auto back = b.unwrap_dek(w1);
        if (!back.has_value() || back->material != m1) return 32;  // v1 retained
        if (b.rotate() != 3) return 33;               // continues from v2
    }
''' % _store(tmp_path), "local_rotate_persist")
    r = _run(b)
    assert r.returncode == 0, r.stdout + r.stderr


def test_phi_at_scale_without_acknowledgment_is_refused(tmp_path):
    b = _compile(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    cfg.phi_at_scale = true;
    cfg.acknowledged = false;

    bool refused = false;
    try {
        LocalKeyProvider kp(cfg);
    } catch (const LocalKeyProviderRefused&) {
        refused = true;
    }
    if (!refused) return 40;

    // and with acknowledgment it proceeds normally
    cfg.acknowledged = true;
    LocalKeyProvider ok(cfg);
    if (ok.active_kek_version() != 1) return 41;
    auto back = ok.unwrap_dek(ok.wrap_dek(ok.generate_dek()));
    if (!back.has_value()) return 42;
''' % _store(tmp_path), "local_ack_gate")
    r = _run(b)
    assert r.returncode == 0, r.stdout + r.stderr


def test_not_at_scale_proceeds_without_acknowledgment(tmp_path):
    b = _compile(tmp_path, '''
    using namespace harpia::crypto;
    LocalKeyProviderConfig cfg;
    cfg.storage_path = "%s";
    cfg.phi_at_scale = false;
    cfg.acknowledged = false;                   // gate only bites at scale
    LocalKeyProvider kp(cfg);
    auto back = kp.unwrap_dek(kp.wrap_dek(kp.generate_dek()));
    if (!back.has_value()) return 50;
''' % _store(tmp_path), "local_not_at_scale")
    r = _run(b)
    assert r.returncode == 0, r.stdout + r.stderr


def test_acknowledgment_env_helper(tmp_path):
    b = _compile(tmp_path, '''
    return harpia::crypto::local_key_provider_acknowledged() ? 0 : 1;
''', "ack_env")
    assert _run(b, {"HARPIA_ACK_LOCAL_KEY_PROVIDER": "1"}).returncode == 0
    assert _run(b, {"HARPIA_ACK_LOCAL_KEY_PROVIDER": "true"}).returncode == 0
    assert _run(b, {"HARPIA_ACK_LOCAL_KEY_PROVIDER": "0"}).returncode == 1
    # unset
    env = dict(os.environ)
    env.pop("HARPIA_ACK_LOCAL_KEY_PROVIDER", None)
    assert subprocess.run([str(b)], env=env).returncode == 1
