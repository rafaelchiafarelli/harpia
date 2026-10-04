"""multi-system-reference / reference-system task 1 -- the dev PKI scripts can
address a server on another machine and issue identities in bulk.

`Assets/cmake/mtls_provision.sh` gains (additively; the positional usage is
covered unchanged by test_mtls_provision.py):
  * `--san <dns-or-ip>` (repeatable) -- extra server SANs (LAN IP, hostname,
    10.0.2.2 for the Android emulator);
  * `--clients-file <path>` -- "<identity> <role>" per line -> one client cert
    each + `rbac_map.txt` (HARPIA_RBAC_MAP format);
  * idempotent re-runs: the CA and existing identities are reused, not re-keyed.
`Assets/cmake/zmq_zap_provision.sh` gains the same `--clients-file` (role
ignored) -> one CURVE keypair per identity + `allowlist.txt`
(HARPIA_ZMQ_ALLOWLIST format), also idempotent.
"""
import hashlib
import os
import re
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
MTLS = os.path.join(REPO_ROOT, "Assets", "cmake", "mtls_provision.sh")
ZAP = os.path.join(REPO_ROOT, "Assets", "cmake", "zmq_zap_provision.sh")

_needs_openssl = pytest.mark.skipif(shutil.which("openssl") is None,
                                    reason="needs openssl")
_needs_zmq = pytest.mark.skipif(
    shutil.which("cc") is None or not os.path.exists("/usr/include/zmq.h"),
    reason="needs cc + libzmq headers (harpia Docker image)")

N = 500
ROLES = ("main", "guest", "admin")
Z85 = re.compile(r"^[0-9a-zA-Z.\-:+=^!/*?&<>()\[\]{}@%$#]{40}$")


def _md5(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def _openssl(*args):
    return subprocess.run(["openssl", *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="module")
def clients_file(tmp_path_factory):
    p = tmp_path_factory.mktemp("clients") / "clients.txt"
    lines = ["# identities for the reference system", ""]
    lines += ["id{:03d} {}".format(i, ROLES[i % 3]) for i in range(N)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


@pytest.fixture(scope="module")
def bulk_pki(tmp_path_factory, clients_file):
    if shutil.which("openssl") is None:
        pytest.skip("needs openssl")
    out = str(tmp_path_factory.mktemp("bulk") / "pki")
    r = subprocess.run(["sh", MTLS, out, "station.example", "--san", "10.0.2.2",
                        "--san", "192.168.1.50", "--san", "station.lan",
                        "--clients-file", clients_file],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    return out


@_needs_openssl
def test_extra_sans_in_server_cert(bulk_pki):
    text = _openssl("x509", "-in", os.path.join(bulk_pki, "server.pem"), "-noout", "-text")
    for want in ("DNS:station.example", "DNS:localhost", "IP Address:127.0.0.1",
                 "IP Address:10.0.2.2", "IP Address:192.168.1.50", "DNS:station.lan"):
        assert want in text, want
    v = subprocess.run(["openssl", "verify", "-CAfile", os.path.join(bulk_pki, "ca.pem"),
                        os.path.join(bulk_pki, "server.pem")], capture_output=True, text=True)
    assert v.returncode == 0, v.stderr


@_needs_openssl
def test_bulk_identities_and_rbac_map(bulk_pki):
    with open(os.path.join(bulk_pki, "rbac_map.txt")) as f:
        rows = [ln.split() for ln in f.read().splitlines()]
    assert len(rows) == N
    assert all(len(r) == 2 and r[1] in ROLES for r in rows)
    assert rows[0] == ["id000", "main"] and rows[1] == ["id001", "guest"]
    for i in (0, 123, N - 1):
        ident = "id{:03d}".format(i)
        cert = os.path.join(bulk_pki, "client_{}.pem".format(ident))
        assert os.path.isfile(os.path.join(bulk_pki, "client_{}_key.pem".format(ident)))
        subj = _openssl("x509", "-in", cert, "-noout", "-subject")
        assert "CN = {}".format(ident) in subj or "CN={}".format(ident) in subj
        assert "TLS Web Client Authentication" in _openssl("x509", "-in", cert, "-noout", "-text")
    # every identity has a cert that verifies against the CA, distinct serials
    certs = [os.path.join(bulk_pki, "client_id{:03d}.pem".format(i)) for i in range(N)]
    serials = {_openssl("x509", "-in", c, "-noout", "-serial") for c in certs[:50]}
    assert len(serials) == 50
    v = subprocess.run(["openssl", "verify", "-CAfile", os.path.join(bulk_pki, "ca.pem"), *certs],
                       capture_output=True, text=True)
    assert v.returncode == 0, v.stderr[-2000:]
    # the first identity doubles as the unqualified client.pem (unchanged convention)
    assert _md5(os.path.join(bulk_pki, "client.pem")) == _md5(certs[0])


@_needs_openssl
def test_rerun_keeps_ca_and_identities(bulk_pki, clients_file, tmp_path):
    before = {n: _md5(os.path.join(bulk_pki, n))
              for n in ("ca.pem", "ca_key.pem", "client_id007.pem", "client_id007_key.pem")}
    extra = tmp_path / "more.txt"
    with open(clients_file) as f:
        extra.write_text(f.read() + "newcomer admin\n", encoding="utf-8")
    r = subprocess.run(["sh", MTLS, bulk_pki, "station.example", "--clients-file", str(extra)],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "1 new, {} kept".format(N) in r.stdout, r.stdout
    for n, h in before.items():
        assert _md5(os.path.join(bulk_pki, n)) == h, n + " was re-keyed"
    with open(os.path.join(bulk_pki, "rbac_map.txt")) as f:
        assert f.read().splitlines()[-1] == "newcomer admin"


@_needs_openssl
@pytest.mark.parametrize("line", ["bad id main", "ok superuser", "with/slash main", "lonely"])
def test_bad_clients_file_line_is_refused(tmp_path, line):
    f = tmp_path / "c.txt"
    f.write_text("good main\n" + line + "\n", encoding="utf-8")
    r = subprocess.run(["sh", MTLS, str(tmp_path / "pki"), "--clients-file", str(f)],
                       capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "c.txt:2" in r.stderr


@_needs_zmq
def test_zmq_bulk_keys_allowlist_and_rerun(tmp_path, clients_file):
    out = str(tmp_path / "zmq")
    r = subprocess.run(["sh", ZAP, out, "--clients-file", clients_file],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    with open(os.path.join(out, "allowlist.txt")) as f:
        rows = [ln.split(" ") for ln in f.read().splitlines()]
    assert len(rows) == N
    assert all(len(r) == 2 and Z85.match(r[0]) for r in rows)
    assert [r[1] for r in rows] == ["id{:03d}".format(i) for i in range(N)]
    assert len({r[0] for r in rows}) == N
    for i in (0, N - 1):
        with open(os.path.join(out, "zmq_id{:03d}_public.key".format(i))) as f:
            assert f.read().strip() == rows[i][0]
        with open(os.path.join(out, "zmq_id{:03d}_secret.key".format(i))) as f:
            assert Z85.match(f.read().strip())
    keep = {n: _md5(os.path.join(out, n))
            for n in ("zmq_server_secret.key", "zmq_id042_public.key", "zmq_id042_secret.key")}
    r = subprocess.run(["sh", ZAP, out, "--clients-file", clients_file],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "(0 new)" in r.stdout
    for n, h in keep.items():
        assert _md5(os.path.join(out, n)) == h, n + " was re-keyed"
