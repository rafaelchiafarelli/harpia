"""python-target / py-zmq task 3: ``harpia_runtime.delivery`` (port of
``harpia_delivery.h``) and the queued ``critical`` sender
(``harpia_runtime.zmq_delivery.QueuedSender``). Mirrors
``test_delivery_runtime.py`` and ``test_critical_delivery_roundtrip.py``.

Runtime (copied runtimes, isolated import): CRC-32 is IEEE (``123456789`` →
``0xCBF43926``) and equals the C++ ``detail::crc32`` on varied payloads
[g++]; ``crc_ok`` catches a mutated payload; every ``check_on_arrival``
outcome; FIFO within capacity; overflow rotates the oldest with one
``queue_rotated`` audit each (observable outcome, rotations,
last_rotated_seq); ``peek`` is non-destructive; capacity 0 → 1; the
mailbox overwrite is audited; the default sink is used when none is given.
Generated project (pyzmq): ``alarm_event`` (``critical event``) publishes
into the queue while no subscriber exists (socket untouched), ``flush``
after the subscriber joins delivers all N in seq order with only the payload
on the wire; capacity 4 + a 10-message burst rotates 6 (audited) and
``flush`` delivers the newest 4; non-critical ``courier``'s sender has no
``flush``/``pending``/``queue`` and ``send`` stays ``bool``.
"""
import importlib
import os
import shutil
import subprocess
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from Compliance.audit_common import PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC  # noqa: E402
from Compliance.delivery_common import (DELIVERY_RUNTIME_SRC,  # noqa: E402
                                        PY_DELIVERY_MODULE, PY_DELIVERY_RUNTIME_SRC)
from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests._py_runtime_load import load_runtime  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"
PK = "ID_" + HASH


@pytest.fixture(scope="module")
def mods(tmp_path_factory):
    return load_runtime(tmp_path_factory.mktemp("py_delivery"),
                        [(PY_DELIVERY_MODULE, PY_DELIVERY_RUNTIME_SRC),
                         (PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC)],
                        [PY_DELIVERY_MODULE, PY_AUDIT_SINK_MODULE])


@pytest.fixture(scope="module")
def d(mods):
    return mods[PY_DELIVERY_MODULE]


def _sink(base):
    class Sink(base):
        def __init__(self):
            self.records = []

        def record(self, operation, subject, detail=""):
            self.records.append((operation, subject, detail))
    return Sink()


PAYLOADS = [b"", b"a", b"123456789", bytes(range(256)), b"\x00" * 1000,
            "José ✓".encode()]


def test_crc_ieee_vector_and_crc_ok(d):
    assert d.crc32(b"123456789") == 0xCBF43926
    e = d.Envelope.stamp(7, b"payload")
    assert e.seq == 7 and e.crc_ok() and e.crc != 0
    bad = d.Envelope(e.seq, e.crc, b"paYload")
    assert not bad.crc_ok()
    assert d.Envelope.stamp(1, b"x").crc == d.Envelope.stamp(2, b"x").crc  # payload only


@pytest.mark.skipif(shutil.which("g++") is None, reason="needs g++")
def test_crc_equals_cpp(d, tmp_path):
    src = tmp_path / "c.cpp"
    src.write_text('#include <cstdio>\n#include <string>\n#include "harpia_delivery.h"\n'
                   'int main(int argc, char** argv) {\n'
                   '  for (int i = 1; i < argc; ++i) { std::string h = argv[i], b;\n'
                   '    for (size_t j = 0; j + 1 < h.size(); j += 2)\n'
                   '      b += (char)std::stoi(h.substr(j, 2), nullptr, 16);\n'
                   '    std::printf("%u\\n", harpia::delivery::detail::crc32(b)); }\n}\n')
    exe = tmp_path / "c"
    c = subprocess.run(["g++", "-std=c++17", "-I", os.path.dirname(DELIVERY_RUNTIME_SRC),
                        str(src), "-o", str(exe)], capture_output=True, text=True, timeout=300)
    assert c.returncode == 0, c.stderr
    out = subprocess.run([str(exe)] + [p.hex() or "x" for p in PAYLOADS],
                         capture_output=True, text=True, check=True).stdout.split()
    assert [int(x) for x in out] == [d.crc32(p) for p in PAYLOADS]


def test_check_on_arrival(d):
    ok = d.Envelope.stamp(5, b"x")
    assert d.check_on_arrival(ok, 5) is d.Arrival.OK
    assert d.check_on_arrival(ok, 3) is d.Arrival.SEQ_GAP
    assert d.check_on_arrival(ok, 9) is d.Arrival.SEQ_REGRESSED
    assert d.check_on_arrival(d.Envelope(5, ok.crc ^ 1, b"x"), 5) is d.Arrival.CRC_MISMATCH


def test_queue_fifo_rotation_peek_and_clamp(d, mods):
    sink = _sink(mods[PY_AUDIT_SINK_MODULE].AuditSink)
    q = d.BoundedQueue(3, sink, "alarm_event")
    outcomes = [q.push(d.Envelope.stamp(i, b"p%d" % i)) for i in range(1, 6)]
    assert outcomes == [d.PushOutcome.ACCEPTED] * 3 + [d.PushOutcome.ROTATED_OLDEST] * 2
    assert q.rotations() == 2 and q.last_rotated_seq() == 2 and q.size() == 3
    assert sink.records == [("queue_rotated", "alarm_event", "dropped_seq=1"),
                            ("queue_rotated", "alarm_event", "dropped_seq=2")]
    assert q.peek().seq == 3 and q.peek().seq == 3 and q.size() == 3
    assert [q.pop().seq for _ in range(3)] == [3, 4, 5] and q.pop() is None and q.empty()
    z = d.BoundedQueue(0)
    assert z.capacity() == 1
    z.push(d.Envelope.stamp(1, b"a"))
    assert z.push(d.Envelope.stamp(2, b"b")) is d.PushOutcome.ROTATED_OLDEST


def test_mailbox_and_default_sink(d, mods):
    sink = _sink(mods[PY_AUDIT_SINK_MODULE].AuditSink)
    mb = d.Mailbox(sink, "vitals")
    assert mb.put(d.Envelope.stamp(1, b"a")) is d.PutOutcome.STORED
    assert mb.put(d.Envelope.stamp(2, b"b")) is d.PutOutcome.OVERWROTE
    assert sink.records == [("mailbox_overwritten", "vitals", "superseded_seq=1")]
    assert mb.overwrites() == 1 and mb.last_overwritten_seq() == 1
    assert mb.take().seq == 2 and not mb.has_pending() and mb.take() is None
    q = d.BoundedQueue(1)
    assert q._audit is mods[PY_AUDIT_SINK_MODULE].default_audit_sink()


# -- generated critical publisher ------------------------------------------------

@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    if not P.HAVE_PY or not P._importable("zmq"):
        pytest.skip(P.SKIP_PY + " + pyzmq")
    g = P.generate_python(tmp_path_factory.mktemp("py_critical"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture()
def ctx(gen):
    import zmq
    c = zmq.Context()
    yield c
    c.destroy(linger=0)  # no ZAP handler here: plaintext only


def _z(name):
    return importlib.import_module("harpia_generated.zmq.{}_{}_zmq".format(name, HASH))


def _alarm(i):
    m = _z("alarm_event").alarm_event()
    setattr(m, PK, i)
    return m


def _drain(sub, n, ms=3000):
    import zmq
    sub.socket.setsockopt(zmq.RCVTIMEO, ms)
    out = []
    for _ in range(n):
        m = sub.receive()
        if m is None:
            break
        out.append(getattr(m, PK))
    return out


_SETTLE_S = 0.3  # PUB/SUB subscription settle, as the C++ round-trip test


def test_stall_then_flush_delivers_all_in_order(ctx):
    z = _z("alarm_event")
    pub = z.new_publisher(ctx, "inproc://crit1")
    outcomes = [pub.publish(_alarm(i)) for i in range(1, 6)]  # nobody listening yet
    assert all(o is not None and o.name == "ACCEPTED" for o in outcomes)
    assert pub.pending() == 5
    sub = z.new_subscriber(ctx, "inproc://crit1")
    time.sleep(_SETTLE_S)
    assert pub.flush() == 5 and pub.pending() == 0
    assert _drain(sub, 5) == [1, 2, 3, 4, 5]
    pub.close()
    sub.close()


def test_overflow_rotates_audited_and_flush_sends_newest(ctx, gen):
    from harpia_runtime.compliance.audit_sink import AuditSink
    sink = _sink(AuditSink)
    z = _z("alarm_event")
    pub = z.new_publisher(ctx, "inproc://crit2", queue_capacity=4, audit_sink=sink)
    sub = z.new_subscriber(ctx, "inproc://crit2")
    time.sleep(_SETTLE_S)
    outcomes = [pub.publish(_alarm(i)).name for i in range(1, 11)]
    assert outcomes.count("ROTATED_OLDEST") == 6 and pub.pending() == 4
    assert pub.queue().rotations() == 6 and pub.queue().last_rotated_seq() == 6
    assert sink.records == [("queue_rotated", "alarm_event", "dropped_seq=%d" % i)
                            for i in range(1, 7)]
    assert pub.flush() == 4
    assert _drain(sub, 4) == [7, 8, 9, 10]
    pub.close()
    sub.close()


def test_only_the_payload_goes_on_the_wire(ctx):
    import zmq
    z = _z("alarm_event")
    pub = z.new_publisher(ctx, "inproc://crit3")
    raw = ctx.socket(zmq.SUB)
    raw.connect("inproc://crit3")
    raw.setsockopt(zmq.SUBSCRIBE, b"")
    raw.setsockopt(zmq.RCVTIMEO, 3000)
    time.sleep(_SETTLE_S)
    pub.publish(_alarm(42))
    pub.flush()
    frames = raw.recv_multipart()
    assert len(frames) == 1
    got = z.alarm_event.FromString(frames[0])
    assert getattr(got, PK) == 42
    raw.close(linger=0)
    pub.close()


def test_non_critical_sender_unchanged(ctx):
    s = _z("courier").new_sender(ctx, "inproc://plain")
    assert not any(hasattr(s, a) for a in ("flush", "pending", "queue"))
    assert type(s).__name__ == "Sender"
    s.close()
