"""Stage 13 (DDS transport) -- a third selectable transport alongside gRPC and
ZMQ, for messages that need to cross an ASTM F2761 / OpenICE-class DDS bus
(dds-transport epic). Mirrors ZmqAdapter's shape.

For each message that declares the `dds` transport modifier, emit a
header-only C++ transport over Eclipse Cyclone DDS (ddscxx) that moves the
message as a serialized-protobuf frame -- the same wire payload ZMQ / gRPC
use -- on one opaque, keyed topic type (`harpia_dds::Frame`):

    <name>_publisher  : DomainParticipant + Topic + Publisher + DataWriter,
                        publish(const Msg&)  -> serialize, wrap, write
    <name>_subscriber : DomainParticipant + Topic + Subscriber + DataReader,
                        receive(Msg*)        -> take, unwrap, parse

QoS mapping (harpia_sensitive_data_design_rules.md §4, a schema-level choice
never inferred at runtime):

  - `critical` message type  -> §4a ordered/complete:
        RELIABILITY = RELIABLE, HISTORY = KEEP_ALL, bounded by
        RESOURCE_LIMITS(max_samples = QUEUE_DEPTH) -- the same
        overflow-is-a-limit-hit reasoning as the ZMQ path's BoundedQueue.
  - everything else          -> §4b latest-value-only:
        RELIABILITY = BEST_EFFORT, HISTORY = KEEP_LAST(1).

DURABILITY stays VOLATILE either way -- TRANSIENT_LOCAL late-joiner catch-up
is a per-use-case open question (task 2b note), not defaulted on here.

Output: <dest>/generated/cpp/dds/<name>_<hash>_dds.h, plus -- when at least
one `dds` message exists -- the shared frame IDL + its CMake scaffolding
copied into the same directory (harpia_dds_frame.idl + CMakeLists.txt), so a
consumer just `add_subdirectory(generated/cpp/dds)` and links
`harpia_dds_transport`.

Out of scope (later tasks): DDS-Security wiring (task 3), `phi` field
AuditSink wiring over DDS (task 4).
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate, write_if_different, copy_if_different
from Compliance.dds_common import (
    DDS_FRAME_IDL, DDS_FRAME_IDL_SRC, DDS_FRAME_HEADER,
    DDS_FRAME_NAMESPACE, DDS_FRAME_TYPE)

DDS_EXT = "_dds.h"

#: §4a bound on a `critical` writer's retained history -- mirrors
#: ZmqAdapter's BoundedQueue default `queue_capacity` (128), the same
#: "overflow is a resource-limit hit, not an unbounded buffer" reasoning.
QUEUE_DEPTH = 128

_HEADER = loadTemplate(__file__, "header.h.tmpl")
_QOS = loadTemplate(__file__, "qos.tmpl")
_PUBSUB = loadTemplate(__file__, "pubsub.tmpl")

# CMake scaffolding copied next to the generated headers (turns the frame IDL
# into C++ via idlc + idlcxx and rolls it up with ddscxx).
_FRAME_CMAKE = "CMakeLists.txt"
_FRAME_CMAKE_SRC = os.path.join(os.path.dirname(DDS_FRAME_IDL_SRC), _FRAME_CMAKE)

_CRITICAL_WRITER = (
    "    qos << ::dds::core::policy::Reliability::Reliable(\n"
    "               ::dds::core::Duration::from_secs(10));\n"
    "    qos << ::dds::core::policy::History::KeepAll();\n"
    "    qos << ::dds::core::policy::ResourceLimits(\n"
    "               {depth}, ::dds::core::LENGTH_UNLIMITED,\n"
    "               ::dds::core::LENGTH_UNLIMITED);\n".format(depth=QUEUE_DEPTH)
)
# reader mirrors the writer so a RELIABLE writer actually matches it
_CRITICAL_READER = _CRITICAL_WRITER
_LATEST_WRITER = (
    "    qos << ::dds::core::policy::Reliability::BestEffort();\n"
    "    qos << ::dds::core::policy::History::KeepLast(1);\n"
)
_LATEST_READER = _LATEST_WRITER


class DdsAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "dds")
        self.log = logger(outFile=None, moduleName="DdsAdapter")

    @staticmethod
    def _modifiers(msg):
        mods = getattr(msg, "access_modifiers", None) or []
        return {m[0] for m in mods}

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            if "DDS" not in self._modifiers(msg):
                continue
            is_critical = bool(getattr(msg, "is_critical", False))
            header = self._render(msg, is_critical)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, DDS_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1

        if written == 0:
            self.log.print("no `dds` transport-bearing messages; no DDS adapters")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        # The shared frame type + its build scaffolding land once, next to the
        # per-message headers (mirrors the delivery runtime's single home).
        copy_if_different(DDS_FRAME_IDL_SRC,
                          os.path.join(self.outDir, DDS_FRAME_IDL))
        copy_if_different(_FRAME_CMAKE_SRC,
                          os.path.join(self.outDir, _FRAME_CMAKE))

        self.log.print("generated {} DDS transport(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg, is_critical):
        guard = "HARPIA_DDS_{}_{}".format(msg.name.upper(), msg.md5Hash)
        pb = "protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash)
        cls = msg.name

        if is_critical:
            profile_note = ("§4a ordered/complete: RELIABLE + KEEP_ALL, bounded "
                            "by RESOURCE_LIMITS (`critical` message type)")
            writer_pol, reader_pol = _CRITICAL_WRITER, _CRITICAL_READER
        else:
            profile_note = ("§4b latest-value-only: BEST_EFFORT + KEEP_LAST(1) "
                            "(non-`critical` message type)")
            writer_pol, reader_pol = _LATEST_WRITER, _LATEST_READER

        qos_block = _QOS.format(name=msg.name, profile_note=profile_note,
                                writer_policies=writer_pol,
                                reader_policies=reader_pol)

        body = _PUBSUB.format(
            comment="// `dds`{crit}: {n}_publisher writes onto topic \"{n}\", "
                    "{n}_subscriber reads from it.".format(
                        n=msg.name,
                        crit=" + `critical`" if is_critical else ""),
            name=msg.name, topic=msg.name, cls=cls,
            frame_ns=DDS_FRAME_NAMESPACE, frame_type=DDS_FRAME_TYPE)

        return _HEADER.format(guard=guard, frame_header=DDS_FRAME_HEADER,
                              pb_header=pb, qos_block=qos_block, body=body)
