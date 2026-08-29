"""dds-transport epic, task 2b: DdsAdapter emits a per-message DDS transport
for every `dds`-tagged message, and maps the delivery-guarantee split from
`harpia_sensitive_data_design_rules.md` §4 onto DDS QoS at the schema level:

  - `critical` message type -> §4a: RELIABILITY=RELIABLE, HISTORY=KEEP_ALL,
    bounded by RESOURCE_LIMITS.
  - non-`critical`          -> §4b: RELIABILITY=BEST_EFFORT,
    HISTORY=KEEP_LAST(1).

Pure Python / structural -- runs the real pipeline (UnitTests/run_pipeline.py,
no C++ toolchain) and inspects the emitted dds/ headers. The compile-and-run
proof is `test_dds_demo.py`.

Fixtures (HarpiaTest/Include/file3.harpia): `alarm_event` is
`critical event dds` (critical QoS profile); `vitals_publication` is a plain
`dds` message (latest-value profile); `courier`/`users`/`patient_vitals` are
not `dds` (no DDS header).
"""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
RUNNER = os.path.join(HERE, "run_pipeline.py")
HASH = "3ac5d8b36fc7dcfb70888145147ddfb7"


@pytest.fixture(scope="module")
def dds_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("harpia_dds_qos")
    r = subprocess.run([sys.executable, RUNNER, str(out)],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return os.path.join(str(out), "build", "generated", "cpp", "dds")


def _read(d, name):
    with open(os.path.join(d, name), encoding="utf-8") as f:
        return f.read()


def test_only_dds_messages_get_a_header(dds_dir):
    names = sorted(n for n in os.listdir(dds_dir) if n.endswith("_dds.h"))
    assert names == [
        "alarm_event_{}_dds.h".format(HASH),
        "vitals_publication_{}_dds.h".format(HASH),
    ]


def test_shared_frame_scaffolding_copied(dds_dir):
    assert os.path.isfile(os.path.join(dds_dir, "harpia_dds_frame.idl"))
    assert os.path.isfile(os.path.join(dds_dir, "CMakeLists.txt"))
    cml = _read(dds_dir, "CMakeLists.txt")
    assert "idlcxx_generate(" in cml
    assert "harpia_dds_transport" in cml


def test_critical_message_maps_to_reliable_keep_all(dds_dir):
    h = _read(dds_dir, "alarm_event_{}_dds.h".format(HASH))
    assert "alarm_event_writer_qos" in h and "alarm_event_reader_qos" in h
    assert "::dds::core::policy::Reliability::Reliable(" in h
    assert "::dds::core::policy::History::KeepAll();" in h
    assert "::dds::core::policy::ResourceLimits(" in h
    # §4b must NOT leak into a critical header
    assert "BestEffort()" not in h
    assert "KeepLast(1)" not in h
    # publisher/subscriber pair, publish/receive verbs, opaque frame payload
    assert "class alarm_event_publisher" in h
    assert "class alarm_event_subscriber" in h
    assert "bool publish(const ::alarm_event& msg)" in h
    assert "bool receive(::alarm_event* msg)" in h
    assert "::harpia_dds::Frame" in h


def test_non_critical_message_maps_to_best_effort_keep_last(dds_dir):
    h = _read(dds_dir, "vitals_publication_{}_dds.h".format(HASH))
    assert "::dds::core::policy::Reliability::BestEffort();" in h
    assert "::dds::core::policy::History::KeepLast(1);" in h
    # §4a must NOT leak into a latest-value header
    assert "Reliable(" not in h
    assert "KeepAll()" not in h
    assert "ResourceLimits(" not in h
    assert "class vitals_publication_publisher" in h
    assert "class vitals_publication_subscriber" in h


def test_durability_left_volatile(dds_dir):
    # TRANSIENT_LOCAL late-joiner catch-up is a per-use-case open question
    # (task 2b) -- it must not be defaulted on in either profile.
    for name in ("alarm_event_{}_dds.h".format(HASH),
                 "vitals_publication_{}_dds.h".format(HASH)):
        h = _read(dds_dir, name)
        assert "TransientLocal" not in h
        assert "Durability" not in h
