"""python-target / py-dds task 1: DDS pub/sub over the shared
``harpia_dds::Frame`` topic type (``harpia_runtime.dds.frame`` /
``.transport`` + generated ``harpia_generated/dds/*_dds.py``).

- the module set equals the C++ ``dds/*_dds.h`` set; ``Frame`` is
  ``harpia_dds::Frame``, ``@appendable``, keyed on ``message_type``;
- Python publisher → Python subscriber for both fixture messages (in order,
  one sample per ``receive``), ``receive`` times out with ``None``, an
  unparsable payload is consumed and gives ``None``;
- C++ publisher → Python subscriber and Python publisher → C++ subscriber on
  the same topic (the generated C++ headers, built with CycloneDDS-CXX) --
  proof that the Python ``Frame`` type matches ``ddscxx``'s;
- task 2, QoS: each generated class's profile follows ``critical`` exactly
  as the C++ header's (reliable / keep-all / 128 vs best-effort /
  keep-last(1), reader = writer); under a stalled reader the ``critical``
  burst survives complete and in order while the other collapses to at most
  the newest (``test_dds_demo.py``'s check); a reliable C++ writer delivers
  every sample to a Python reader and the reverse.

Every test uses its own topic name so concurrent runs on one host don't
cross-talk on domain 0.
"""
import importlib
import os
import shutil
import subprocess
import sys
import time
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from UnitTests import _py_cpp_parity as P  # noqa: E402
from UnitTests.test_dds_demo import _cyclonedds_cxx_findable  # noqa: E402

HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"


def _have_cyclonedds_py():
    try:
        importlib.import_module("cyclonedds.domain")
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(not P.HAVE_PY or not _have_cyclonedds_py(),
                                reason=P.SKIP_PY + " + cyclonedds")
_cpp = pytest.mark.skipif(any(shutil.which(t) is None for t in ("cmake", "g++"))
                          or not _cyclonedds_cxx_findable(),
                          reason="needs cmake + g++ + installed CycloneDDS-CXX")


@pytest.fixture(scope="module")
def gen(tmp_path_factory):
    g = P.generate_python(tmp_path_factory.mktemp("py_dds"))
    P.fixture_messages(P.py_root(g))
    return g


@pytest.fixture()
def use(gen):
    P.activate(P.py_root(gen))
    return gen


def _mod(path):
    return importlib.import_module(path.format(h=HASH))


def _dds(name):
    return _mod("harpia_generated.dds.%s_{h}_dds" % name)


def _topic(name):
    return "%s_%s" % (name, uuid.uuid4().hex[:12])


def _alarm(i):
    m = _mod("harpia_generated.protofiles.alarm_event_{h}_pb2").alarm_event()
    m.patient_id, m.alarm_type, m.severity = "p-py", "apnea", i
    return m


def _vitals(i):
    m = _mod("harpia_generated.protofiles.vitals_publication_{h}_pb2").vitals_publication()
    m.patient_ref, m.spo2, m.pulse_rate = "p-py", 97.5, i
    return m


def test_module_set_and_frame_type(use):
    cpp = {f[:-len("_dds.h")] for f in os.listdir(os.path.join(use, "generated", "cpp", "dds"))
           if f.endswith("_dds.h")}
    py = {f[:-len("_dds.py")] for f in os.listdir(os.path.join(P.py_root(use),
                                                                "harpia_generated", "dds"))
          if f.endswith("_dds.py")}
    assert py == cpp == {"alarm_event_" + HASH, "vitals_publication_" + HASH}
    frame = _mod("harpia_runtime.dds.frame").Frame
    idl = frame.__idl__
    assert idl.idl_transformed_typename == "harpia_dds::Frame"
    assert frame.__idl_annotations__ == {"extensibility": "appendable"}
    assert frame.__idl_field_annotations__ == {"message_type": {"key": True}}


def test_qos_follows_critical_like_cpp(use):
    from cyclonedds.qos import Policy
    hdr_dir = os.path.join(use, "generated", "cpp", "dds")
    for name in ("alarm_event", "vitals_publication"):
        header = open(os.path.join(hdr_dir, "%s_%s_dds.h" % (name, HASH))).read()
        critical = "KeepAll" in header
        for role in ("publisher", "subscriber"):
            cls = getattr(_dds(name), "%s_%s" % (name, role))
            assert cls.CRITICAL is critical
            assert cls.reader_qos() == cls.writer_qos()
            qos = cls.writer_qos()
            if critical:
                assert qos[Policy.Reliability] == Policy.Reliability.Reliable(
                    max_blocking_time=10 * 10 ** 9)
                assert qos[Policy.History] == Policy.History.KeepAll
                assert qos[Policy.ResourceLimits] == Policy.ResourceLimits(
                    max_samples=128, max_instances=-1, max_samples_per_instance=-1)
                assert "ResourceLimits(\n               128," in header
            else:
                assert qos[Policy.Reliability] == Policy.Reliability.BestEffort
                assert qos[Policy.History] == Policy.History.KeepLast(1)
                assert "BestEffort()" in header and "KeepLast(1)" in header
    assert _dds("alarm_event").alarm_event_publisher.CRITICAL  # the fixture's critical one


def _wait_match(*endpoints, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all((e.matched_subscribers() if hasattr(e, "matched_subscribers")
                else e.matched_publishers()) > 0 for e in endpoints):
            return
        time.sleep(0.02)
    pytest.fail("endpoints never matched")


def test_stalled_reader_semantics(use):
    from cyclonedds.domain import DomainParticipant
    dp = DomainParticipant()
    ta, tv = _topic("alarm_event"), _topic("vitals_publication")
    crit_pub = _dds("alarm_event").alarm_event_publisher(dp, ta)
    crit_sub = _dds("alarm_event").alarm_event_subscriber(dp, ta)
    best_pub = _dds("vitals_publication").vitals_publication_publisher(dp, tv)
    best_sub = _dds("vitals_publication").vitals_publication_subscriber(dp, tv)
    _wait_match(crit_pub, crit_sub, best_pub, best_sub)
    for i in range(20):  # nobody drains while we send
        crit_pub.publish(_alarm(i))
        best_pub.publish(_vitals(i))
    time.sleep(1.0)
    crit = []
    while (m := crit_sub.receive()) is not None:
        crit.append(m.severity)
    best = []
    while (m := best_sub.receive()) is not None:
        best.append(m.pulse_rate)
    assert crit == list(range(20))
    assert len(best) <= 1 and all(v == 19 for v in best)


def _send_until(pub, sub, make, n, timeout=10.0):
    """Publish ``make(1)`` until the subscriber sees it (discovery), then
    1..n; returns what the subscriber received after the first."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pub.publish(make(0))
        if sub.receive(0.1) is not None:
            break
    else:
        pytest.fail("never matched")
    while sub.receive(0.05) is not None:
        pass
    got = []
    for i in range(1, n + 1):
        assert pub.publish(make(i))
        m = sub.receive(2.0)
        if m is not None:
            got.append(m)
    return got


@pytest.mark.parametrize("name,make,field", [("alarm_event", _alarm, "severity"),
                                             ("vitals_publication", _vitals, "pulse_rate")])
def test_python_round_trip(use, name, make, field):
    from cyclonedds.domain import DomainParticipant
    dp = DomainParticipant()
    topic = _topic(name)
    sub = getattr(_dds(name), name + "_subscriber")(dp, topic)
    pub = getattr(_dds(name), name + "_publisher")(dp, topic)
    got = _send_until(pub, sub, make, 10)
    assert [getattr(m, field) for m in got] == list(range(1, 11))
    assert got[0] == make(1)
    assert sub.receive(0.2) is None


def test_garbage_payload_is_consumed(use):
    from cyclonedds.domain import DomainParticipant
    from cyclonedds.pub import DataWriter
    frame = _mod("harpia_runtime.dds.frame").Frame
    dp = DomainParticipant()
    topic = _topic("vitals_publication")
    sub = _dds("vitals_publication").vitals_publication_subscriber(dp, topic)
    pub = _dds("vitals_publication").vitals_publication_publisher(dp, topic)
    _send_until(pub, sub, _vitals, 0)
    DataWriter(dp, sub.topic).write(frame(message_type="vitals_publication",
                                          payload=b"\xff\xff\xff"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and sub.reader.read(N=1) == []:
        time.sleep(0.01)
    assert sub.receive(0.5) is None
    assert sub.reader.read(N=1) == []


# -- C++ <-> Python ------------------------------------------------------------------

@pytest.fixture(scope="module")
def peer(gen, tmp_path_factory):
    if any(shutil.which(t) is None for t in ("cmake", "g++")) or not _cyclonedds_cxx_findable():
        pytest.skip("needs cmake + g++ + installed CycloneDDS-CXX")
    src = tmp_path_factory.mktemp("dds_peer_src")
    shutil.copytree(os.path.join(HERE, "py_dds_interop"), str(src), dirs_exist_ok=True)
    cpp_in = (src / "dds_peer.cpp.in").read_text()
    (src / "dds_peer.cpp").write_text(cpp_in.replace("@HASH@", HASH))
    build = src / "build"
    cfg = subprocess.run(["cmake", "-S", str(src), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                          "-DHARPIA_GEN=" + os.path.join(gen, "generated", "cpp"),
                          "-DHARPIA_HASH=" + HASH], capture_output=True, text=True)
    assert cfg.returncode == 0, cfg.stdout + cfg.stderr
    bld = subprocess.run(["cmake", "--build", str(build), "-j", str(os.cpu_count() or 2)],
                         capture_output=True, text=True)
    assert bld.returncode == 0, bld.stdout[-3000:] + bld.stderr[-3000:]
    return str(build / "dds_peer")


@_cpp
@pytest.mark.parametrize("kind,name,field", [("alarm", "alarm_event", "severity"),
                                             ("vitals", "vitals_publication", "pulse_rate")])
def test_cpp_publisher_python_subscriber(use, peer, kind, name, field):
    topic = _topic(name)
    sub = getattr(_dds(name), name + "_subscriber")(topic_name=topic)
    proc = subprocess.Popen([peer, "pub", kind, topic, "10"], stdout=subprocess.PIPE, text=True)
    got = []
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and proc.poll() is None:
            m = sub.receive(0.2)
            if m is not None:
                got.append(m)
        while (m := sub.receive(0.2)) is not None:
            got.append(m)
    finally:
        out = proc.communicate(timeout=30)[0]
    assert "PUB_DONE" in out, out
    values = [getattr(m, field) for m in got]
    assert values and values == sorted(values) and set(values) <= set(range(1, 11))
    if kind == "alarm":  # critical: reliable + keep-all on both sides
        assert values == list(range(1, 11))
    assert all(getattr(m, "patient_id" if kind == "alarm" else "patient_ref") == "p-cpp"
               for m in got)


@_cpp
@pytest.mark.parametrize("kind,name,make", [("alarm", "alarm_event", _alarm),
                                            ("vitals", "vitals_publication", _vitals)])
def test_python_publisher_cpp_subscriber(use, peer, kind, name, make):
    topic = _topic(name)
    pub = getattr(_dds(name), name + "_publisher")(topic_name=topic)
    proc = subprocess.Popen([peer, "sub", kind, topic, "3"], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "READY"
        if kind == "alarm":  # critical: once matched, every sample arrives
            _wait_match(pub, timeout=20)
            time.sleep(0.3)
            for i in range(1, 4):
                pub.publish(make(i))
        else:
            deadline = time.monotonic() + 25
            i = 0
            while proc.poll() is None and time.monotonic() < deadline:
                i += 1
                pub.publish(make(i))
                time.sleep(0.05)
    finally:
        out = proc.communicate(timeout=30)[0]
    lines = [line.split() for line in out.splitlines() if line.startswith("GOT ")]
    assert "SUB_DONE 3" in out, out
    assert all(parts[2] == "p-py" for parts in lines)
    values = [int(parts[1]) for parts in lines]
    assert values == sorted(values) and len(set(values)) == 3
    if kind == "alarm":
        assert values == [1, 2, 3]


# -- task 4: phi-over-DDS publish audit ------------------------------------------------

def _sink():
    base = _mod("harpia_runtime.compliance.audit_sink").AuditSink

    class Rec(base):
        def __init__(self):
            self.records = []

        def record(self, operation, subject, detail=""):
            self.records.append((operation, subject, detail))
    return Rec()


@pytest.mark.parametrize("name,make", [("alarm_event", _alarm), ("vitals_publication", _vitals)])
def test_phi_publish_audit_like_cpp(use, name, make):
    import re
    header = open(os.path.join(use, "generated", "cpp", "dds",
                               "%s_%s_dds.h" % (name, HASH))).read()
    want = tuple(re.search(r'audit_\.record\("([^"]+)", "([^"]+)", "([^"]+)"\)',
                           header).groups())
    from cyclonedds.domain import DomainParticipant
    dp = DomainParticipant()
    sink = _sink()
    topic = _topic(name)
    pub = getattr(_dds(name), name + "_publisher")(dp, topic, audit_sink=sink)
    sub = getattr(_dds(name), name + "_subscriber")(dp, topic)
    for i in range(5):
        assert pub.publish(make(i))
    assert sink.records == [want] * 5
    assert all("p-py" not in r[2] for r in sink.records)  # field names, never values
    import inspect
    assert "audit_sink" not in inspect.signature(type(sub).__init__).parameters


def test_phi_audit_records_after_the_write(use):
    from cyclonedds.domain import DomainParticipant
    base = _mod("harpia_runtime.compliance.audit_sink").AuditSink

    class Boom(base):
        def record(self, operation, subject, detail=""):
            raise RuntimeError("sink down")
    dp = DomainParticipant()
    topic = _topic("alarm_event")
    pub = _dds("alarm_event").alarm_event_publisher(dp, topic, audit_sink=Boom())
    sub = _dds("alarm_event").alarm_event_subscriber(dp, topic)
    _wait_match(pub, sub)
    with pytest.raises(RuntimeError):
        pub.publish(_alarm(7))
    got = sub.receive(5.0)  # the write happened before the record
    assert got is not None and got.severity == 7


def test_phi_audit_default_sink(use, monkeypatch):
    sink = _sink()
    monkeypatch.setattr(_mod("harpia_runtime.compliance.audit_sink"), "_DEFAULT_SINK", sink)
    from cyclonedds.domain import DomainParticipant
    pub = _dds("vitals_publication").vitals_publication_publisher(
        DomainParticipant(), _topic("vitals_publication"))
    pub.publish(_vitals(1))
    assert sink.records == [("phi_publish", "vitals_publication", "patient_ref")]


def test_no_phi_dds_message_has_no_audit(tmp_path):
    from PyDds.PyDdsAdapter import PyDdsAdapter

    class _Msg:
        name = "plain_stream"
        md5Hash = "deadbeef"
        isEnum = False
        is_critical = False
        access_modifiers = [("DDS", "dds ")]
        variables = []

    assert PyDdsAdapter(messages=[_Msg()], dest=str(tmp_path)).Process() is None
    py = tmp_path / "python"
    module = (py / "harpia_generated" / "dds" / "plain_stream_deadbeef_dds.py").read_text()
    assert "udit" not in module and "phi" not in module
    assert "class plain_stream_publisher(Publisher[plain_stream]):" in module
    assert not (py / "harpia_runtime" / "dds" / "audit.py").exists()
    assert not (py / "harpia_runtime" / "compliance").exists()
