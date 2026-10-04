"""python-target / py-zmq task 4: the ``stream`` consumer lifecycle
(``harpia_runtime.zmq_stream`` + generated ``<name>_stream``), mirroring the
C++ zmq-lifecycle tests with short windows.

Structural: exactly the ``stream`` messages (the C++ ``<name>_stream``
classes) get a ``<name>_stream`` subclass; ``StreamConfig`` defaults equal
the C++ ``StreamConfig``.
Runtime (pyzmq, generated ``sensor_feed``): bad configs → ``INVALID`` with no
socket opened; read before setup → ``INVALID``; ``OK`` + message; a timed
read → ``TIMEOUT`` without blocking; ``stop`` idempotent, later reads
``STOPPED``, context manager stops; the watchdog trips an idle stream and
latches ``INVALID``; reclamation trips a dead peer first when its window is
shorter; garbage frames keep reclamation away (and read ``INVALID``) but
the watchdog still trips.
"""
import importlib
import os
import re
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402

pytestmark = pytest.mark.skipif(not P.HAVE_PY or not P._importable("zmq"),
                                reason=P.SKIP_PY + " + pyzmq")

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_zmq_stream"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture()
def ctx(gen):
    import zmq
    c = zmq.Context()
    yield c
    c.destroy(linger=0)


def _z(name="sensor_feed"):
    return importlib.import_module("harpia_generated.zmq.{}_{}_zmq".format(name, HASH))


def _s():
    return importlib.import_module("harpia_runtime.zmq_stream")


def test_stream_classes_and_defaults_match_cpp(gen):
    cpp_dir = os.path.join(gen, "generated", "cpp", "zmq")
    cpp = set()
    for f in os.listdir(cpp_dir):
        cpp |= set(re.findall(r"class (\w+)_stream \{", open(os.path.join(cpp_dir, f)).read()))
    py_dir = os.path.join(P.py_root(gen), "harpia_generated", "zmq")
    py = set()
    for f in os.listdir(py_dir):
        py |= set(re.findall(r"class (\w+)_stream\(", open(os.path.join(py_dir, f)).read()))
    assert py == cpp and "sensor_feed" in py
    header = open(os.path.join(cpp_dir, "sensor_feed_{}_zmq.h".format(HASH))).read()
    struct = re.search(r"struct StreamConfig \{(.*?)\};", header, re.S).group(1)
    want = {k: int(v) for k, v in re.findall(r"(\w+_ms|max_records)\s*=\s*(\d+);", struct)}
    assert set(want) == {"read_timeout_ms", "stop_deadline_ms", "reclaim_after_ms",
                         "max_records"}
    c = _s().StreamConfig("tcp://x:1")
    assert {k: getattr(c, k) for k in want} == want and c.topic == ""


@pytest.mark.parametrize("cfg", [
    dict(endpoint=""), dict(endpoint="udp://h:1"), dict(endpoint="host:1"),
    dict(endpoint="inproc://s", read_timeout_ms=0),
    dict(endpoint="inproc://s", stop_deadline_ms=-1),
    dict(endpoint="inproc://s", max_records=0)])
def test_invalid_config_opens_nothing(cfg, ctx):
    s = _z().sensor_feed_stream(ctx)
    assert s.setup(_s().StreamConfig(**cfg)) is _s().StreamStatus.INVALID
    assert s.socket is None and s.state() is _s().StreamStatus.INVALID
    assert s.read().status is _s().StreamStatus.INVALID


def _feed(ctx, ep):
    pub = _z().new_publisher(ctx, ep)
    return pub


def _msg(i):
    m = _z().sensor_feed()
    setattr(m, PK, i)
    m.sensor_id = "s%d" % i
    return m


def test_ok_timeout_and_idempotent_stop(ctx):
    S = _s()
    pub = _feed(ctx, "inproc://st1")
    s = _z().sensor_feed_stream(ctx)
    assert s.setup(S.StreamConfig("inproc://st1", read_timeout_ms=50)) is S.StreamStatus.OK
    got = None
    for _ in range(100):  # slow joiner
        pub.publish(_msg(3))
        r = s.read()
        if r.status is S.StreamStatus.OK:
            got = r.msg
            break
    assert got is not None and got.sensor_id == "s3"
    while s.read(20).status is S.StreamStatus.OK:  # drain the extras
        pass
    t0 = time.monotonic()
    r = s.read(100)
    assert r.status is S.StreamStatus.TIMEOUT and r.msg is None
    assert time.monotonic() - t0 < 2.0
    assert s.stop() is S.StreamStatus.STOPPED and s.stop() is S.StreamStatus.STOPPED
    assert s.read().status is S.StreamStatus.STOPPED and s.socket is None
    with _z().sensor_feed_stream(ctx) as s2:
        s2.setup(S.StreamConfig("inproc://st1"))
    assert s2.state() is S.StreamStatus.STOPPED
    pub.close()


def test_watchdog_trips_an_idle_stream(ctx):
    S = _s()
    s = _z().sensor_feed_stream(ctx)
    s.setup(S.StreamConfig("inproc://nobody", read_timeout_ms=20, stop_deadline_ms=150,
                           reclaim_after_ms=60000))
    deadline = time.monotonic() + 5
    statuses = []
    while time.monotonic() < deadline:
        statuses.append(s.read().status)
        if statuses[-1] is S.StreamStatus.INVALID:
            break
    assert statuses[-1] is S.StreamStatus.INVALID and S.StreamStatus.TIMEOUT in statuses
    assert s.socket is None and s.read().status is S.StreamStatus.INVALID  # latched
    assert s.stop() is S.StreamStatus.STOPPED and s.state() is S.StreamStatus.INVALID


def test_reclamation_trips_first_when_shorter(ctx):
    S = _s()
    s = _z().sensor_feed_stream(ctx)
    s.setup(S.StreamConfig("tcp://127.0.0.1:1", read_timeout_ms=20, stop_deadline_ms=60000,
                           reclaim_after_ms=120))
    time.sleep(0.2)
    assert s.read().status is S.StreamStatus.INVALID and s.socket is None
    assert s.state() is S.StreamStatus.INVALID


def test_garbage_keeps_activity_but_watchdog_trips(ctx):
    import zmq
    S = _s()
    raw = ctx.socket(zmq.PUB)
    raw.bind("inproc://garbage-stream")
    s = _z().sensor_feed_stream(ctx)
    s.setup(S.StreamConfig("inproc://garbage-stream", read_timeout_ms=20,
                           stop_deadline_ms=400, reclaim_after_ms=150))
    time.sleep(0.05)
    statuses = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        raw.send(b"\xff\xff\xff")  # undecodable, but wire activity
        statuses.append(s.read().status)
        if s.state() is S.StreamStatus.INVALID:
            break
        time.sleep(0.01)
    # garbage reads as INVALID without latching; reclamation (150 ms) never
    # fired because frames kept arriving, so the 400 ms watchdog is what tripped
    assert s.state() is S.StreamStatus.INVALID
    assert statuses.count(S.StreamStatus.INVALID) > 1
    assert len(statuses) * 0.01 >= 0.3
    raw.close(linger=0)
