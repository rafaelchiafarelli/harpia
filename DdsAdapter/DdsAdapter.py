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

`phi` audit over DDS (task 4): when a `dds` message carries at least one
`phi` field (Foundation F2), its `<name>_publisher` takes an
`::harpia::compliance::AuditSink&` (defaulted to the shared no-op sink, so a
non-`phi` transport is byte-identical) and every `publish()` records exactly
one value-free `AuditSink` entry -- operation `"phi_publish"`, subject = the
DDS topic name, detail = the comma-joined `phi` field names (never a value,
design-rules Rule 5). Same call pattern the DB path uses
(`phi_create`/`phi_read`/...): the transport changes, the audit obligation
does not. `harpia_audit_sink.h` is copied next to the generated headers when
any emitted `dds` message has a `phi` field.

Output: <dest>/generated/cpp/dds/<name>_<hash>_dds.h, plus -- when at least
one `dds` message exists -- the shared frame IDL + its CMake scaffolding
copied into the same directory (harpia_dds_frame.idl + CMakeLists.txt), so a
consumer just `add_subdirectory(generated/cpp/dds)` and links
`harpia_dds_transport`; plus harpia_audit_sink.h when any `dds` message
carries a `phi` field.

Out of scope (later tasks): DDS-Security wiring (task 3).
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate, write_if_different, copy_if_different
from Compliance.dds_common import (
    DDS_FRAME_IDL, DDS_FRAME_IDL_SRC, DDS_FRAME_HEADER,
    DDS_FRAME_NAMESPACE, DDS_FRAME_TYPE)
from Compliance.audit_common import AUDIT_SINK_RUNTIME, AUDIT_SINK_RUNTIME_SRC

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

# task 4: `phi`-over-DDS audit. A `dds` message with >=1 `phi` field gets a
# publisher that holds an AuditSink& (defaulted, so a non-`phi` transport is
# byte-identical) and records exactly one value-free entry per publish. Same
# shape as CrudlAdapter's _CRYPTO_CTOR_* / _audit() slots.
_AUDIT_INCLUDE = '\n#include "{}"'.format(AUDIT_SINK_RUNTIME)
_AUDIT_CTOR_PARAM = (
    ",\n        ::harpia::compliance::AuditSink& audit = "
    "::harpia::compliance::default_audit_sink()")
_AUDIT_CTOR_INIT = ",\n          audit_(audit)"
_AUDIT_MEMBER = "\n    ::harpia::compliance::AuditSink& audit_;"


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

    @staticmethod
    def _phi_fields(msg):
        """Names of the message's `phi`-tagged fields (Foundation F2,
        `variable.is_phi`) -- the plain names the protobuf descriptor exposes
        at runtime. Empty for a message with no `phi` field, which keeps its
        DDS transport byte-identical to the pre-task-4 output."""
        return [v.name for v in (getattr(msg, "variables", None) or [])
                if getattr(v, "is_phi", False)]

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        phi_seen = False
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            if "DDS" not in self._modifiers(msg):
                continue
            is_critical = bool(getattr(msg, "is_critical", False))
            phi_fields = self._phi_fields(msg)
            header = self._render(msg, is_critical, phi_fields)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, DDS_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1
            if phi_fields:
                phi_seen = True

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

        # task 4: the generated `<name>_dds.h` for a `phi`-bearing message
        # `#include`s "harpia_audit_sink.h" as a same-dir sibling (mirrors the
        # delivery runtime pulling it in next to harpia_delivery.h).
        if phi_seen:
            copy_if_different(AUDIT_SINK_RUNTIME_SRC,
                              os.path.join(self.outDir, AUDIT_SINK_RUNTIME))

        self.log.print("generated {} DDS transport(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg, is_critical, phi_fields=()):
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

        has_phi = bool(phi_fields)
        # one value-free AuditSink entry per publish: operation "phi_publish",
        # subject = the DDS topic name, detail = the comma-joined `phi` field
        # names -- never a value (design-rules Rule 5). Same slot shape as
        # CrudlAdapter._audit(): "" when the message has no `phi` field.
        audit_call = ('        audit_.record("phi_publish", "{t}", "{f}");\n'
                      .format(t=msg.name, f=",".join(phi_fields))
                      if has_phi else "")

        body = _PUBSUB.format(
            comment="// `dds`{crit}: {n}_publisher writes onto topic \"{n}\", "
                    "{n}_subscriber reads from it.".format(
                        n=msg.name,
                        crit=" + `critical`" if is_critical else ""),
            name=msg.name, topic=msg.name, cls=cls,
            frame_ns=DDS_FRAME_NAMESPACE, frame_type=DDS_FRAME_TYPE,
            audit_ctor_param=_AUDIT_CTOR_PARAM if has_phi else "",
            audit_ctor_init=_AUDIT_CTOR_INIT if has_phi else "",
            audit_member=_AUDIT_MEMBER if has_phi else "",
            audit_call=audit_call)

        return _HEADER.format(guard=guard, frame_header=DDS_FRAME_HEADER,
                              audit_include=_AUDIT_INCLUDE if has_phi else "",
                              pb_header=pb, qos_block=qos_block, body=body)
