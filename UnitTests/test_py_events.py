"""python-target / py-events task 1: ``harpia_runtime.events``
(``PyEvents/runtime/events.py``, the port of ``harpia_event_cache.h``) and
the generated ``harpia_generated/events/<name>_<hash>_events.py``.

Structural (pure Python, generated project): one module per ``event``
message (the C++ ``events/`` set), with the C++ cache mode and the phi audit
metadata (``alarm_event`` → ``'alarm_event_table'``, ``'patient_id'``;
non-phi types empty); no ``events`` package without event messages.
Runtime (image-gated, generated message classes): cached replay vs
not-cached; order within one publish; unsubscribe; publish returns before a
slow callback; the replay is a copy; a raising callback is isolated and
audited; phi channels audit ``phi_event_dispatch`` once per publish on the
calling thread (also with no subscriber; never on replay), non-phi never;
``set_audit_sink`` retargets; concurrent subscribe/publish churn delivers
every event and loses no subscription.
"""
import os
import re
import sys
import threading
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    if not P.HAVE_PY:
        pytest.skip(P.SKIP_PY)
    return P.generate_python(tmp_path_factory.mktemp("py_events"))


@pytest.fixture(scope="module")
def msgs(gen):
    return P.fixture_messages(P.py_root(gen))


def _wait(pred, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


class Sink:
    def __init__(self):
        from harpia_runtime.compliance.audit_sink import AuditSink
        self.__class__ = type("Sink", (Sink, AuditSink), {})
        self.records = []
        self.threads = []

    def record(self, operation, subject, detail=""):
        self.records.append((operation, subject, detail))
        self.threads.append(threading.current_thread())


def test_one_module_per_cpp_event_header(gen):
    cpp = {f[:-len("_events.h")] for f in os.listdir(os.path.join(gen, "generated", "cpp",
                                                                  "events"))
           if f.endswith("_events.h")}
    py_dir = os.path.join(P.py_root(gen), "harpia_generated", "events")
    py = {f[:-len("_events.py")] for f in os.listdir(py_dir) if f.endswith("_events.py")}
    assert py == cpp and cpp
    for name in cpp:
        header = open(os.path.join(gen, "generated", "cpp", "events", name + "_events.h")).read()
        mode, subject, fields = re.search(
            r'CacheMode::(\w+), "([^"]*)", "([^"]*)"', header).groups()
        text = open(os.path.join(py_dir, name + "_events.py")).read()
        want = "CacheMode.{}, {!r}, {!r}".format(
            {"Cached": "CACHED", "NotCached": "NOT_CACHED"}[mode], subject, fields)
        assert want in text, name


def test_no_events_package_without_event_messages(tmp_path):
    from PyEvents.PyEventsAdapter import PyEventsAdapter

    class Plain:
        name, md5Hash, isEnum, tableName = "x", "h", False, ""
        access_modifiers = []
    PyEventsAdapter([Plain()], str(tmp_path)).Process()
    assert not os.path.exists(os.path.join(str(tmp_path), "python"))


def _channel(name, mode=None, subject="", fields=""):
    from harpia_runtime.events import CacheMode, EventChannel
    return EventChannel(mode or CacheMode.CACHED, subject, fields)


def _users(msgs, pk):
    m = msgs["users"]()
    setattr(m, PK, pk)
    return m


def test_cached_replay_vs_not_cached(msgs):
    from harpia_runtime.events import CacheMode
    cached, plain = _channel("c"), _channel("n", CacheMode.NOT_CACHED)
    assert cached.cached() and not plain.cached()
    m = _users(msgs, 7)
    cached.publish(m)
    plain.publish(m)
    assert cached.has_last() and not plain.has_last()
    m.name = "mutated after publish"
    got_c, got_n = [], []
    cached.subscribe(got_c.append)
    plain.subscribe(got_n.append)
    assert _wait(lambda: len(got_c) == 1)
    assert getattr(got_c[0], PK) == 7 and got_c[0].name == ""  # a copy
    time.sleep(0.1)
    assert got_n == []
    plain.publish(_users(msgs, 8))
    assert _wait(lambda: [getattr(x, PK) for x in got_n] == [8])


def test_order_and_unsubscribe(msgs):
    ch = _channel("o")
    seen = []
    ids = [ch.subscribe(lambda v, i=i: seen.append(i)) for i in range(5)]
    assert ch.subscriber_count() == 5
    ch.publish(_users(msgs, 1))
    assert _wait(lambda: len(seen) == 5) and seen == [0, 1, 2, 3, 4]
    ch.unsubscribe(ids[2])
    ch.unsubscribe(999)  # unknown: ignored
    seen.clear()
    ch.publish(_users(msgs, 2))
    assert _wait(lambda: len(seen) == 4) and seen == [0, 1, 3, 4]


def test_publish_does_not_block(msgs):
    from harpia_runtime.events import CacheMode
    ch = _channel("s", CacheMode.NOT_CACHED)
    release, done = threading.Event(), []
    ch.subscribe(lambda v: (release.wait(5), done.append(v)))
    t0 = time.monotonic()
    ch.publish(_users(msgs, 1))
    assert time.monotonic() - t0 < 0.5 and done == []
    release.set()
    assert _wait(lambda: len(done) == 1)


def test_raising_callback_isolated_and_audited(msgs):
    ch = _channel("x", subject="tbl")
    sink = Sink()
    ch.set_audit_sink(sink)
    seen = []

    def boom(v):
        raise RuntimeError("callback bug")
    ch.subscribe(seen.append)
    ch.subscribe(boom)
    ch.subscribe(seen.append)
    ch.publish(_users(msgs, 1))  # must not raise
    assert _wait(lambda: len(seen) == 2)
    assert _wait(lambda: sink.records == [("event_callback_exception", "tbl", "")])
    bare = _channel("y")
    bare.set_audit_sink(sink)
    bare.subscribe(boom)
    bare.publish(_users(msgs, 2))
    assert _wait(lambda: sink.records[-1] == ("event_callback_exception", "<event>", ""))


def test_phi_dispatch_audit_on_calling_thread(msgs):
    phi = _channel("p", subject="alarm_event_table", fields="patient_id")
    sink = Sink()
    phi.set_audit_sink(sink)
    phi.publish(_users(msgs, 1))  # no subscriber: still audited
    assert sink.records == [("phi_event_dispatch", "alarm_event_table", "patient_id")]
    assert sink.threads == [threading.current_thread()]
    got = []
    phi.subscribe(got.append)  # cached replay: no audit
    assert _wait(lambda: len(got) == 1) and len(sink.records) == 1
    plain = _channel("q")
    plain.set_audit_sink(sink)
    plain.publish(_users(msgs, 2))
    assert len(sink.records) == 1
    other = Sink()
    phi.set_audit_sink(other)
    phi.publish(_users(msgs, 3))
    assert len(sink.records) == 1 and len(other.records) == 1


def test_generated_accessor_is_a_singleton(gen, msgs):
    import importlib
    mod = importlib.import_module(
        "harpia_generated.events.alarm_event_{}_events".format(HASH))
    assert mod.alarm_event_channel() is mod.alarm_event_channel()
    assert mod.alarm_event_channel().cached()


def test_concurrent_churn(msgs):
    from harpia_runtime.events import CacheMode
    ch = _channel("churn", CacheMode.NOT_CACHED)
    counts = [0] * 8
    lock = threading.Lock()

    def make(i):
        def cb(v):
            with lock:
                counts[i] += 1
        return cb
    ids = []

    def subscriber(i):
        ids.append(ch.subscribe(make(i)))
        for _ in range(50):
            ch.unsubscribe(ch.subscribe(lambda v: None))
    threads = [threading.Thread(target=subscriber, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert ch.subscriber_count() == 8
    pubs = [threading.Thread(target=lambda: [ch.publish(_users(msgs, 1)) for _ in range(25)])
            for _ in range(4)]
    for t in pubs:
        t.start()
    for t in pubs:
        t.join()
    assert _wait(lambda: counts == [100] * 8, timeout=15), counts
