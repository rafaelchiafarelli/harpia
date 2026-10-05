"""python-target / py-crypto-phi task 4: phi encrypt-on-write /
decrypt-on-read + per-op audit in the generated Python DAOs
(``harpia_runtime.db.phi.PhiDao``).

Image-gated (python protobuf + protoc), SQLite, on a generated project:
- only phi-bearing DAOs (``patient_vitals``, ``alarm_event``) subclass
  ``PhiDao`` and list ``PHI_FIELDS``; the others import no crypto; the
  crypto runtimes are copied because the fixture has phi columns;
- a ``patient_vitals`` row stores ``patient_id`` (string) and
  ``heart_rate`` (float) as ``enc:v1:`` text, non-phi ``device_note`` in
  the clear, and reads back as plaintext (``read`` and ``list``);
- exactly one audit record per operation -- ``phi_create`` / ``phi_read`` /
  ``phi_update`` / ``phi_delete`` / ``phi_list``, subject the table, detail
  the phi column names -- and no value anywhere; a not-found ``read`` audits
  nothing, ``update`` / ``remove`` of a missing row still audit (as C++);
- a caller-supplied ``LocalKeyProvider`` is used (another provider can't
  read the value); a non-phi DAO is unaffected.
g++ + SOCI: over one SQLite file and one ``LocalKeyProvider`` store, a row
written by the C++ ``patient_vitals_dao`` reads in Python and the reverse.
"""
import importlib
import os
import sqlite3
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH
PHI_DAOS = {"patient_vitals", "alarm_event"}


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_phi"))
    P.fixture_messages(P.py_root(g))
    return g


def _mod(name):
    return importlib.import_module("harpia_generated.db.{}_{}_dao".format(name, HASH))


class Recording:
    def __init__(self, base):
        self.records = []
        self.__class__ = type("RecordingSink", (Recording, base), {})

    def record(self, operation, subject, detail=""):
        self.records.append((operation, subject, detail))


def _sink():
    from harpia_runtime.compliance.audit_sink import AuditSink
    return Recording(AuditSink)


def _vitals(pk, patient="patient-7781", rate=72.5, note="stable"):
    m = _mod("patient_vitals").patient_vitals()
    setattr(m, PK, pk)
    m.patient_id, m.heart_rate, m.device_note = patient, rate, note
    return m


def _dao(conn, **kw):
    dao = _mod("patient_vitals").patient_vitals_dao(conn, **kw)
    dao.create_table()
    return dao


def test_only_phi_daos_use_phidao(gen):
    root = os.path.join(P.py_root(gen), "harpia_generated", "db")
    for f in sorted(os.listdir(root)):
        if not f.endswith("_dao.py"):
            continue
        name = f[:-len("_{}_dao.py".format(HASH))]
        text = open(os.path.join(root, f)).read()
        assert ("PhiDao" in text) == (name in PHI_DAOS), name
        assert ("crypto" in text) is False
    assert _mod("patient_vitals").patient_vitals_dao.PHI_FIELDS == ("patient_id", "heart_rate")
    for m in ("encrypted_column", "key_provider", "key_provider_local", "key_provider_kms"):
        assert os.path.exists(os.path.join(P.py_root(gen), "harpia_runtime", "crypto", m + ".py"))


def test_encrypted_at_rest_plaintext_on_read(gen, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    dao = _dao(conn)
    assert dao.create(_vitals(1))
    pid, rate, note = conn.execute(
        'SELECT "patient_id", "heart_rate", "device_note" FROM "patient_vitals_table"').fetchone()
    assert pid.startswith("enc:v1:") and rate.startswith("enc:v1:") and note == "stable"
    assert "patient-7781" not in pid
    got = _mod("patient_vitals").patient_vitals()
    assert dao.read(1, got)
    assert (got.patient_id, got.heart_rate, got.device_note) == ("patient-7781", 72.5, "stable")
    assert [(m.patient_id, m.heart_rate) for m in dao.list()] == [("patient-7781", 72.5)]
    assert [m.patient_id for m in dao.list(0, 1)] == ["patient-7781"]


def test_one_audit_per_op_names_only(gen, tmp_path):
    sink = _sink()
    dao = _dao(sqlite3.connect(str(tmp_path / "db.sqlite")), audit_sink=sink)
    t, f = "patient_vitals_table", "patient_id,heart_rate"
    dao.create(_vitals(1))
    dao.read(1, _mod("patient_vitals").patient_vitals())
    assert not dao.read(99, _mod("patient_vitals").patient_vitals())  # audits nothing
    dao.update(_vitals(1, patient="patient-0002", rate=80.0))
    dao.list()
    dao.list(0, 5)
    dao.remove(1)
    assert not dao.update(_vitals(42))  # missing row: still audited, as C++
    assert not dao.remove(42)
    assert sink.records == [
        ("phi_create", t, f), ("phi_read", t, f), ("phi_update", t, f),
        ("phi_list", t, f), ("phi_list", t, f), ("phi_delete", t, f),
        ("phi_update", t, f), ("phi_delete", t, f),
    ]
    for record in sink.records:
        for arg in record:
            for value in ("patient-7781", "patient-0002", "72.5", "80.0", "enc:v1:"):
                assert value not in arg


def test_caller_key_provider_is_used(gen, tmp_path):
    from harpia_runtime.crypto.encrypted_column import decrypt_field, default_key_provider
    from harpia_runtime.crypto.key_provider_local import (LocalKeyProvider,
                                                          LocalKeyProviderConfig)
    kp = LocalKeyProvider(LocalKeyProviderConfig(str(tmp_path / "keks")))
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    _dao(conn, key_provider=kp).create(_vitals(5))
    stored = conn.execute('SELECT "patient_id" FROM "patient_vitals_table"').fetchone()[0]
    assert decrypt_field(kp, stored) == "patient-7781"
    assert decrypt_field(default_key_provider(), stored) != "patient-7781"
    again = LocalKeyProvider(LocalKeyProviderConfig(str(tmp_path / "keks")))  # restart
    got = _mod("patient_vitals").patient_vitals()
    assert _dao(conn, key_provider=again).read(5, got) and got.patient_id == "patient-7781"


def test_non_phi_dao_unaffected(gen, tmp_path):
    users = _mod("users")
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    dao = users.users_dao(conn)
    dao.create_table()
    m = users.users()
    setattr(m, PK, 1)
    m.name = "neo"
    assert dao.create(m)
    assert conn.execute('SELECT "name" FROM "user_table"').fetchone()[0] == "neo"
    with pytest.raises(TypeError):
        users.users_dao(conn, key_provider=None)


HAVE_SOCI = P.HAVE_CPP and os.path.exists("/usr/include/soci/soci.h")

_CPP = r'''
#include <cstdio>
#include <string>
#include <soci/soci.h>
#include <soci/sqlite3/soci-sqlite3.h>
#include "db/patient_vitals_%(h)s_crudl.h"
#include "crypto/harpia_key_provider_local.h"
int main(int, char** argv) {
    ::soci::session db(::soci::sqlite3, argv[1]);
    harpia::crypto::LocalKeyProvider kp(harpia::crypto::LocalKeyProviderConfig{argv[2], false, false});
    harpia::db::patient_vitals_dao dao(db, kp);
    std::string mode = argv[3];
    if (mode == "write") {
        dao.create_table();
        ::patient_vitals m; m.set_id_%(h)s(3); m.set_patient_id("cpp-patient");
        m.set_heart_rate(61.25f); m.set_device_note("from c++");
        return dao.create(m) ? 0 : 3;
    }
    ::patient_vitals got;
    if (!dao.read(std::stoll(argv[4]), &got)) return 4;
    std::printf("%%s|%%.2f|%%s\n", got.patient_id().c_str(), got.heart_rate(),
                got.device_note().c_str());
    return 0;
}
'''


@pytest.fixture(scope="module")
def cpp_vitals(gen, tmp_path_factory):
    if not HAVE_SOCI:
        pytest.skip("needs g++ + SOCI sqlite3 + protobuf")
    cpp_root = os.path.join(gen, "generated", "cpp")
    d = tmp_path_factory.mktemp("cpp_phi")
    (d / "x.cpp").write_text(_CPP % {"h": HASH})
    flags = subprocess.run(["pkg-config", "--cflags", "--libs", "protobuf"],
                           capture_output=True, text=True, check=True).stdout.split()
    pb = os.path.join(cpp_root, "protofiles", "patient_vitals_{}.pb.cc".format(HASH))
    exe = d / "x"
    c = subprocess.run(["g++", "-std=c++17", "-I", cpp_root, str(d / "x.cpp"), pb, "-o", str(exe),
                        "-lsoci_core", "-lsoci_sqlite3", *flags, "-lpthread", "-ldl"],
                       capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    return str(exe)


def test_cpp_writes_python_reads_and_back(gen, cpp_vitals, tmp_path):
    from harpia_runtime.crypto.key_provider_local import (LocalKeyProvider,
                                                          LocalKeyProviderConfig)
    db, store = tmp_path / "shared.sqlite", tmp_path / "shared.keks"
    subprocess.run([cpp_vitals, str(db), str(store), "write"], check=True, timeout=60)
    conn = sqlite3.connect(str(db))
    assert conn.execute('SELECT "patient_id" FROM "patient_vitals_table"').fetchone()[0] \
        .startswith("enc:v1:")
    kp = LocalKeyProvider(LocalKeyProviderConfig(str(store)))
    dao = _dao(conn, key_provider=kp)
    got = _mod("patient_vitals").patient_vitals()
    assert dao.read(3, got)
    assert (got.patient_id, got.heart_rate, got.device_note) == ("cpp-patient", 61.25, "from c++")
    assert dao.create(_vitals(4, patient="py-patient", rate=58.5, note="from python"))
    out = subprocess.run([cpp_vitals, str(db), str(store), "read", "4"], capture_output=True,
                         text=True, check=True, timeout=60).stdout.strip()
    assert out == "py-patient|58.50|from python"
