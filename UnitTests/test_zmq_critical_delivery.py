"""Phase 3b (sensitive-data roadmap): ZmqAdapter routes a `critical` message
type's send path through the delivery-guarantee runtime's bounded rotating
queue, and leaves every non-`critical` transport byte-for-byte as it was.

Pure Python / structural -- runs the real pipeline (UnitTests/run_pipeline.py,
no C++ toolchain) and inspects the emitted zmq/ headers plus the copied
delivery/ runtime. The compile-and-run proof is Phase 3c (test_stage13_zmq
already compiles every generated zmq header, alarm_event's included).

Fixture: HarpiaTest/Include/file3.harpia -- `alarm_event` is `critical event`
(so its publisher is the critical one); `patient_vitals`/`courier`/`users`
are not critical.
"""
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_zmq_critical")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    cpp = os.path.join(str(out), "build", "generated", "cpp")
    return {
        "zmq": os.path.join(cpp, "zmq"),
        "delivery": os.path.join(cpp, "delivery"),
    }


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_critical_publisher_wires_the_bounded_queue(generated):
    h = _read(os.path.join(generated["zmq"],
                           "alarm_event_{}_zmq.h".format(HASH)))
    # pulls in the shared runtime at file scope
    assert '#include "delivery/harpia_delivery.h"' in h
    # the publisher holds a BoundedQueue and a per-sender seq counter
    assert "::harpia::delivery::BoundedQueue queue_;" in h
    assert "std::uint64_t next_seq_ = 1;" in h
    # subject passed to the queue is the message type name (audit trail)
    assert 'queue_(queue_capacity, audit, "alarm_event")' in h
    # publish() enqueues a stamped Envelope instead of firing the socket
    assert ("::std::optional<::harpia::delivery::PushOutcome> "
            "publish(const ::alarm_event& msg)") in h
    assert "::harpia::delivery::Envelope::stamp(" in h
    # a separate flush() is what actually drains to the wire, oldest-first
    assert "std::size_t flush() {" in h
    assert "queue_.peek()" in h and "queue_.pop();" in h
    # the direct socket send that the non-critical publisher used is gone
    assert "return socket_.send(frame, ::zmq::send_flags::none).has_value();" \
        not in h.split("std::size_t flush()")[0]


def test_critical_subscriber_is_untouched(generated):
    h = _read(os.path.join(generated["zmq"],
                           "alarm_event_{}_zmq.h".format(HASH)))
    # the receiving half gets no queue -- Phase 3b only wires the send path
    sub = h[h.index("class alarm_event_subscriber"):]
    assert "BoundedQueue" not in sub
    assert "bool receive(::alarm_event* msg)" in sub


def test_noncritical_transport_headers_are_unchanged(generated):
    for name in ("courier", "users"):
        h = _read(os.path.join(generated["zmq"],
                               "{}_{}_zmq.h".format(name, HASH)))
        assert "harpia_delivery.h" not in h
        assert "BoundedQueue" not in h
        assert "delivery::" not in h
        # still the plain bool sender API
        assert "BoundedQueue" not in h


def test_delivery_runtime_and_its_audit_dep_are_copied(generated):
    d = generated["delivery"]
    assert os.path.isfile(os.path.join(d, "harpia_delivery.h"))
    # harpia_delivery.h #includes "harpia_audit_sink.h" at the same relative
    # path, so the dependency must land beside it
    assert os.path.isfile(os.path.join(d, "harpia_audit_sink.h"))
    # copies are verbatim -- same bytes as the repo source
    assert _read(os.path.join(d, "harpia_delivery.h")) == _read(os.path.join(
        REPO_ROOT, "Compliance", "runtime", "harpia_delivery.h"))


def test_delivery_dir_absent_when_no_critical_message(tmp_path):
    # Drive ZmqAdapter directly with a single non-critical push message: no
    # delivery/ directory should be created at all.
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    from ZmqAdapter.ZmqAdapter import ZmqAdapter

    class _Msg:
        name = "plain_ping"
        md5Hash = "deadbeef"
        isEnum = False
        is_critical = False
        access_modifiers = [("PUSH", "push ")]
        variables = []

    dest = str(tmp_path)
    assert ZmqAdapter(messages=[_Msg()], dest=dest).Process() is None
    assert os.path.isfile(os.path.join(
        dest, "generated", "cpp", "zmq", "plain_ping_deadbeef_zmq.h"))
    assert not os.path.exists(os.path.join(
        dest, "generated", "cpp", "delivery"))
