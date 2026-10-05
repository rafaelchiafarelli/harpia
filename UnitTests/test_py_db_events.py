"""python-target / py-events task 2: DAO OnChange. A table-bearing
``event`` message's generated DAO publishes each committed ``create`` /
``update`` to ``<name>_channel()`` (never ``read`` / ``list`` /
``remove``); a phi+event DAO also records ``phi_event_onchange`` right
after the publish.

Image-gated, generated project, SQLite:
- ``users`` (event): create / update fire exactly one callback each,
  read / list / remove none; an update of a missing row still publishes
  (C++ publishes after any update);
- the publish happens only after commit: a failing create (duplicate key)
  publishes nothing, and a dbio import fires one event per row after its
  single transaction;
- ``alarm_event`` (event + phi): one ``phi_event_onchange`` per change,
  after the channel's own ``phi_event_dispatch``, names only;
- non-event DAOs (``beacon_log``, phi non-event ``patient_vitals``) have no
  OnChange hook and import no events module.
"""
import importlib
import os
import sqlite3
import sys
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY, reason=P.SKIP_PY)

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_db_events"))
    P.fixture_messages(P.py_root(g))
    return g


def _mod(kind, name):
    return importlib.import_module("harpia_generated.{0}.{1}_{2}_{0}".format(
        kind, name, HASH) if kind != "db" else
        "harpia_generated.db.{}_{}_dao".format(name, HASH))


def _channel(name):
    return getattr(_mod("events", name), name + "_channel")()


class Sink:
    def __init__(self):
        from harpia_runtime.compliance.audit_sink import AuditSink
        self.__class__ = type("Sink", (Sink, AuditSink), {})
        self.records = []

    def record(self, operation, subject, detail=""):
        self.records.append((operation, subject, detail))


def _settle(seen, n, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end and len(seen) < n:
        time.sleep(0.01)
    time.sleep(0.1)  # and nothing more arrives
    return len(seen)


@pytest.fixture()
def users(gen, tmp_path):
    mod = _mod("db", "users")
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    dao = mod.users_dao(conn)
    dao.create_table()
    seen, lock = [], threading.Lock()

    def cb(m):
        with lock:
            seen.append((getattr(m, PK), m.name))
    replay = _channel("users").has_last()  # cached: an earlier test's value replays
    sub = _channel("users").subscribe(cb)
    if replay:
        assert _settle(seen, 1) == 1
    seen.clear()
    yield mod, dao, seen
    _channel("users").unsubscribe(sub)


def _user(mod, pk, name):
    m = mod.users()
    setattr(m, PK, pk)
    m.name = name
    return m


def test_create_update_fire_read_list_remove_dont(users):
    mod, dao, seen = users
    assert dao.create(_user(mod, 1, "neo"))
    assert _settle(seen, 1) == 1 and seen == [(1, "neo")]
    assert dao.update(_user(mod, 1, "thomas"))
    assert _settle(seen, 2) == 2 and seen[-1] == (1, "thomas")
    dao.read(1, mod.users())
    dao.list()
    dao.list(0, 1)
    dao.remove(1)
    assert _settle(seen, 3, 0.3) == 2
    assert not dao.update(_user(mod, 99, "ghost"))  # no row: C++ still publishes
    assert _settle(seen, 3) == 3 and seen[-1] == (99, "ghost")


def test_rolled_back_create_publishes_nothing(users):
    mod, dao, seen = users
    assert dao.create(_user(mod, 5, "first"))
    assert _settle(seen, 1) == 1
    with pytest.raises(sqlite3.IntegrityError):
        dao.create(_user(mod, 5, "duplicate"))
    assert _settle(seen, 2, 0.3) == 1


def test_dbio_import_fires_after_its_transaction(users, gen):
    mod, dao, seen = users
    io = _mod("dbio", "users")
    text = "".join(
        __import__("harpia_runtime.json", fromlist=["to_json"]).to_json(_user(mod, i, "u%d" % i))
        + "\n" for i in (10, 11, 12))
    assert io.import_json(dao, text) == 3
    assert _settle(seen, 3) == 3 and sorted(seen) == [(10, "u10"), (11, "u11"), (12, "u12")]


def test_phi_event_dao_records_onchange(gen, tmp_path):
    mod = _mod("db", "alarm_event")
    sink = Sink()
    _channel("alarm_event").set_audit_sink(sink)
    try:
        dao = mod.alarm_event_dao(sqlite3.connect(str(tmp_path / "db.sqlite")), audit_sink=sink)
        dao.create_table()
        m = mod.alarm_event()
        setattr(m, PK, 1)
        m.patient_id = "patient-xyz"
        dao.create(m)
        m.patient_id = "patient-abc"
        dao.update(m)
        dao.read(1, mod.alarm_event())
        dao.remove(1)
    finally:
        from harpia_runtime.compliance.audit_sink import default_audit_sink
        _channel("alarm_event").set_audit_sink(default_audit_sink())
    t, f = "alarm_event_table", "patient_id"
    assert sink.records == [
        ("phi_create", t, f), ("phi_event_dispatch", t, f), ("phi_event_onchange", t, f),
        ("phi_update", t, f), ("phi_event_dispatch", t, f), ("phi_event_onchange", t, f),
        ("phi_read", t, f), ("phi_delete", t, f),
    ]
    assert not any("patient-" in a for r in sink.records for a in r)


def test_non_event_daos_untouched(gen):
    root = os.path.join(P.py_root(gen), "harpia_generated", "db")
    for name in ("beacon_log", "patient_vitals"):
        text = open(os.path.join(root, "{}_{}_dao.py".format(name, HASH))).read()
        assert "_on_change" not in text and "harpia_generated.events" not in text
    users = open(os.path.join(root, "users_{}_dao.py".format(HASH))).read()
    assert "users_channel().publish(msg)" in users and "phi_event_onchange" not in users
