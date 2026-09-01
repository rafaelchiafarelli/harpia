"""transport-authn epic, task 1 -- the mTLS client-cert PKI provisioning
script (Assets/cmake/mtls_provision.sh), the mTLS analogue of
Assets/cmake/dds_security_provision.sh.

Two layers, same split as test_dds_security.py:
  - structural / pure Python (always): the script ships, is executable, and
    is copied into a generated project's tree with `-DUSE_MTLS` wired into
    the top-level CMakeLists.
  - openssl-backed (needs `openssl` on PATH): run the script and inspect the
    PKI it mints -- CA + server cert + client cert(s), `openssl verify`
    against the CA, client subject CN == the identity argument, key strength
    tracking HARPIA_MTLS_PROVIDER, and the graceful no-openssl / no-args
    failures.
"""
import os
import shutil
import stat
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
SCRIPT = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")

_needs_openssl = pytest.mark.skipif(
    shutil.which("openssl") is None, reason="needs openssl on PATH")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _x509(*args):
    return subprocess.run(["openssl", "x509", *args],
                          capture_output=True, text=True, check=True).stdout


# --------------------------------------------------------------------------
# structural -- pure Python, always runs
# --------------------------------------------------------------------------

def test_script_present_and_executable():
    assert os.path.isfile(SCRIPT)
    assert os.stat(SCRIPT).st_mode & stat.S_IXUSR
    body = _read(SCRIPT)
    assert "openssl req -x509" in body            # mints the CA
    assert "openssl x509 -req" in body            # signs the leaf certs
    assert "extendedKeyUsage=serverAuth" in body
    assert "extendedKeyUsage=clientAuth" in body
    assert "NOT a production identity store" in body   # honest header block


def test_copied_into_generated_tree(tmp_path):
    r = subprocess.run([sys.executable, RUNNER, str(tmp_path)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    copied = os.path.join(str(tmp_path), "build", "cmake", "mtls_provision.sh")
    assert os.path.isfile(copied), "mtls_provision.sh not copied into the build tree"
    assert os.stat(copied).st_mode & stat.S_IXUSR, "copied script lost its +x bit"
    cmake = _read(os.path.join(str(tmp_path), "build", "CMakeLists.txt"))
    assert 'option(USE_MTLS' in cmake
    assert "harpia_mtls_files.h" in cmake
    assert "mtls_provision.sh" in cmake


# --------------------------------------------------------------------------
# openssl-backed
# --------------------------------------------------------------------------

@_needs_openssl
def test_mints_ca_server_and_client(tmp_path):
    out = tmp_path / "pki"
    r = subprocess.run(["sh", SCRIPT, str(out), "svc.example", "alpha", "beta"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr

    for f in ("ca.pem", "ca_key.pem", "server.pem", "server_key.pem",
              "client.pem", "client_key.pem",
              "client_alpha.pem", "client_alpha_key.pem",
              "client_beta.pem", "client_beta_key.pem"):
        assert (out / f).is_file(), f + " missing"

    # both leaf certs chain to the minted CA
    v = subprocess.run(["openssl", "verify", "-CAfile", str(out / "ca.pem"),
                        str(out / "server.pem"), str(out / "client_alpha.pem"),
                        str(out / "client_beta.pem")],
                       capture_output=True, text=True)
    assert v.returncode == 0, v.stdout + v.stderr

    # the first named identity is also the unqualified client.pem
    assert _read(str(out / "client.pem")) == _read(str(out / "client_alpha.pem"))

    # client subject CN is exactly the identity argument -- task 4 maps this to a role
    subj = _x509("-in", str(out / "client_beta.pem"), "-noout", "-subject")
    assert "CN = beta" in subj or "CN=beta" in subj

    # EKUs distinguish the two roles in the handshake
    assert "TLS Web Server Authentication" in _x509(
        "-in", str(out / "server.pem"), "-noout", "-ext", "extendedKeyUsage")
    assert "TLS Web Client Authentication" in _x509(
        "-in", str(out / "client.pem"), "-noout", "-ext", "extendedKeyUsage")

    # server cert carries a SAN (a bare CN is rejected by modern TLS stacks)
    san = _x509("-in", str(out / "server.pem"), "-noout", "-ext", "subjectAltName")
    assert "svc.example" in san and "127.0.0.1" in san


@_needs_openssl
def test_default_identity_when_none_named(tmp_path):
    out = tmp_path / "pki"
    r = subprocess.run(["sh", SCRIPT, str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    subj = _x509("-in", str(out / "client.pem"), "-noout", "-subject")
    assert "harpia-client" in subj


@_needs_openssl
@pytest.mark.parametrize("provider,bits,sig", [
    (None, "2048 bit", "sha256"),
    ("default", "2048 bit", "sha256"),
    ("fips", "3072 bit", "sha384"),
])
def test_key_params_track_provider(tmp_path, provider, bits, sig):
    out = tmp_path / "pki"
    env = dict(os.environ)
    if provider is None:
        env.pop("HARPIA_MTLS_PROVIDER", None)
    else:
        env["HARPIA_MTLS_PROVIDER"] = provider
    r = subprocess.run(["sh", SCRIPT, str(out)], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    text = _x509("-in", str(out / "server.pem"), "-noout", "-text")
    assert bits in text
    assert (sig + "withrsaencryption") in text.lower()


@_needs_openssl
def test_missing_openssl_fails_cleanly(tmp_path):
    out = tmp_path / "pki"
    # a PATH with no openssl -- keep sh resolvable via an absolute interpreter
    r = subprocess.run(["/bin/sh", SCRIPT, str(out)],
                       capture_output=True, text=True,
                       env={"PATH": "/nonexistent"})
    assert r.returncode != 0
    assert "openssl not found" in (r.stdout + r.stderr)
    assert not out.exists(), "no partial PKI dir should be left behind"


@_needs_openssl
def test_no_args_is_a_usage_error():
    r = subprocess.run(["sh", SCRIPT], capture_output=True, text=True)
    assert r.returncode == 2
    assert "usage:" in (r.stdout + r.stderr)
