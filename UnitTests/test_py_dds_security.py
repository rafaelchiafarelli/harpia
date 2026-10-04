"""python-target / py-dds task 3: DDS-Security (``harpia_runtime.dds.security``).

- structural: incomplete ``SecurityFiles`` → ``SecurityRefused``; a domain
  that already exists unsecured in the process → ``SecurityRefused`` (never a
  plaintext participant); the Cyclone ``<Security>`` configuration is
  byte-identical to ``harpia_dds_security.h``'s [C++ peer]; the
  governance / permissions / selection documents in
  ``harpia_generated/dds/security/`` are the C++ ones, byte for byte;
- live (``test_dds_security.py``'s demo across languages), one PKI from
  ``dds_security_provision.sh`` over the Python copies of the documents, on
  a per-test domain id: a secured C++ publisher reaches a secured Python
  subscriber while a plain Python subscriber receives nothing, and a
  secured Python publisher reaches a secured C++ subscriber while a plain
  C++ subscriber receives nothing. Python participants run in their own
  processes (the secured domain configuration is per process, as in C++).
"""
import importlib
import os
import random
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests import test_py_dds as D  # noqa: E402

pytestmark = D.pytestmark
HASH = D.HASH
PROVISION = os.path.join(REPO_ROOT, "Assets", "cmake", "dds_security_provision.sh")
gen = D.gen
use = D.use
peer = D.peer


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


def _sec():
    return _mod("harpia_runtime.dds.security")


@pytest.fixture(scope="module")
def certs(gen, tmp_path_factory):
    if shutil.which("openssl") is None:
        pytest.skip("needs openssl")
    sec = os.path.join(P.py_root(gen), "harpia_generated", "dds", "security")
    out = str(tmp_path_factory.mktemp("dds_pki"))
    p = subprocess.run(["sh", PROVISION, out, os.path.join(sec, "governance.xml"),
                        os.path.join(sec, "permissions.xml")], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    return out


def _files(d):
    return _sec().SecurityFiles(*(os.path.join(d, f) for f in (
        "identity_ca.pem", "identity_certificate.pem", "private_key.pem",
        "permissions_ca.pem", "governance.p7s", "permissions.p7s")))


def test_refuses_incomplete_files(use):
    sec = _sec()
    for files in (sec.SecurityFiles(), sec.SecurityFiles("ca", "cert", "key", "pca", "gov", "")):
        assert not files.complete()
        with pytest.raises(sec.SecurityRefused):
            sec.secured_participant(7, files)


def test_refuses_an_existing_plain_domain(use, certs):
    from cyclonedds.domain import DomainParticipant
    sec = _sec()
    domain = random.randint(100, 199)
    plain = DomainParticipant(domain)
    with pytest.raises(sec.SecurityRefused):
        sec.secured_participant(domain, _files(certs))
    del plain


def test_security_documents_are_the_cpp_ones(use):
    cpp = os.path.join(use, "generated", "cpp", "dds", "security")
    py = os.path.join(P.py_root(use), "harpia_generated", "dds", "security")
    names = ("governance.xml", "permissions.xml", "dds_security_selection.json")
    assert sorted(os.listdir(py)) == sorted(names)
    for name in names:
        assert open(os.path.join(py, name), "rb").read() == \
            open(os.path.join(cpp, name), "rb").read()


def test_config_xml_matches_cpp(use, peer, certs):
    cpp = subprocess.run([peer, "xml", "-", "-", "0", certs], capture_output=True, text=True,
                         check=True).stdout
    assert _sec().security_config_xml(_files(certs), "fips") == cpp
    odd = _sec().SecurityFiles('a&b<c>"d\'', "x", "y", "z", "g", "p")
    assert '<IdentityCA>file:a&amp;b&lt;c&gt;&quot;d\'</IdentityCA>' in \
        _sec().security_config_xml(odd)


_PY_PEER = r'''
import glob, importlib, os, sys, time
root, mode, topic, n, certs, domain, run_s = sys.argv[1:8]
n, domain, run_s = int(n), int(domain), float(run_s)
sys.path.insert(0, root)
stem = os.path.basename(glob.glob(os.path.join(
    root, "harpia_generated", "dds", "alarm_event_*_dds.py"))[0])[:-3]
mod = importlib.import_module("harpia_generated.dds." + stem)
pb2 = importlib.import_module("harpia_generated.protofiles." + stem[:-4] + "_pb2")
from cyclonedds.domain import DomainParticipant
from harpia_runtime.dds import security as S
if certs == "-":
    dp = DomainParticipant(domain)
else:
    dp = S.secured_participant(domain, S.SecurityFiles(*(os.path.join(certs, f) for f in (
        "identity_ca.pem", "identity_certificate.pem", "private_key.pem",
        "permissions_ca.pem", "governance.p7s", "permissions.p7s"))))
if mode == "sub":
    sub = mod.alarm_event_subscriber(dp, topic)
    print("READY", flush=True)
    got, end = [], time.monotonic() + run_s
    while len(got) < n and time.monotonic() < end:
        m = sub.receive(0.1)
        if m is not None:
            got.append(m.severity)
    print("GOT", len(got), *got, flush=True)
else:
    pub = mod.alarm_event_publisher(dp, topic)
    end = time.monotonic() + 25
    while pub.matched_subscribers() == 0 and time.monotonic() < end:
        time.sleep(0.02)
    if pub.matched_subscribers() == 0:
        print("NOMATCH", flush=True)
        sys.exit(1)
    time.sleep(0.3)
    for i in range(1, n + 1):
        pub.publish(pb2.alarm_event(patient_id="p-py", alarm_type="apnea", severity=i))
        time.sleep(0.02)
    time.sleep(1.0)
    print("PUB_DONE", flush=True)
'''


def _py_peer(gen, mode, n, certs, domain, run_s=20):
    return subprocess.Popen([sys.executable, "-c", _PY_PEER, P.py_root(gen), mode, "alarm_event",
                             str(n), certs, str(domain), str(run_s)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _env(domain):
    return {**os.environ, "HARPIA_DDS_DOMAIN": str(domain)}


def _done(proc, timeout=60):
    out, err = proc.communicate(timeout=timeout)
    return out, err


@D._cpp
def test_secured_cpp_publisher_to_python(use, peer, certs):
    domain = random.randint(1, 99)
    secured = _py_peer(use, "sub", 5, certs, domain)
    plain = _py_peer(use, "sub", 5, "-", domain, run_s=12)
    try:
        assert secured.stdout.readline().strip() == "READY"
        assert plain.stdout.readline().strip() == "READY"
        pub = subprocess.run([peer, "pub", "alarm", "alarm_event", "5", certs],
                             capture_output=True, text=True, timeout=60, env=_env(domain))
        assert "PUB_DONE" in pub.stdout, pub.stdout + pub.stderr
    finally:
        s_out, s_err = _done(secured)
        p_out, p_err = _done(plain)
    assert s_out.split() == ["GOT", "5", "1", "2", "3", "4", "5"], s_out + s_err
    assert p_out.split() == ["GOT", "0"], p_out + p_err


@D._cpp
def test_secured_python_publisher_to_cpp(use, peer, certs):
    domain = random.randint(1, 99)
    secured = subprocess.Popen([peer, "sub", "alarm", "alarm_event", "5", certs],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               env=_env(domain))
    plain = subprocess.Popen([peer, "sub", "alarm", "alarm_event", "5"],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=_env(domain))
    try:
        assert secured.stdout.readline().strip() == "READY"
        assert plain.stdout.readline().strip() == "READY"
        pub = _py_peer(use, "pub", 5, certs, domain)
        out, err = _done(pub)
        assert "PUB_DONE" in out, out + err
    finally:
        s_out, s_err = _done(secured)
        p_out, p_err = _done(plain)
    got = [int(line.split()[1]) for line in s_out.splitlines() if line.startswith("GOT ")]
    assert got == [1, 2, 3, 4, 5] and "SUB_DONE 5" in s_out, s_out + s_err
    assert "SUB_DONE 0" in p_out and "GOT " not in p_out, p_out + p_err
