"""Stage 13 (ZMQ/socket transport) -- raw-socket alternative to the gRPC path.

For each message that declares a transport modifier, emit a header-only C++ ZMQ
transport over cppzmq that moves the message as a serialized-protobuf frame:

  - PUSH/PULL  (spec 12.1, push/pull functions)  when the message is push/pull
        <name>_sender    : PUSH socket, connect(endpoint), send(const Msg&)
        <name>_receiver  : PULL socket, bind(endpoint),    recv(Msg*)

  - PUB/SUB    (spec 12.2, streaming functions)  when the message is event/stream
        <name>_publisher : PUB socket,  bind(endpoint),    publish(const Msg&)
        <name>_subscriber: SUB socket,  connect(endpoint), receive(Msg*)

Message originator / unique sender number (process.md 1.3.1.1)
--------------------------------------------------------------
Every sender/publisher carries an origin id and stamps it into the message's
ORIGINATOR field before sending, so each message is attributable to the sender
that registered it:

  - one-to-* (unique publisher: message has PULL/EVENT/STREAM): the id is a
    COMPILE-TIME constant derived from the file hash + message name
    (origin_id()) -- the sender's default constructor uses it.
  - many-to-* (shared publisher: message has only PUSH/PUSHPULL): the id is
    assigned at RUNTIME so concurrent senders are distinguishable -- the
    sender's default constructor calls runtime_origin_id() (pid + a
    per-process counter + random bits; decentralized, no broker needed). The
    explicit-origin constructor still exists for a caller with its own id
    (e.g. a future broker), but nothing requires one.

_is_one_to_many() below makes this same one-to-* vs many-to-* call that
Message.py already makes for ORIGINATOR field naming (isOneToMany).

Output: <dest>/generated/cpp/zmq/<name>_<hash>_zmq.h, including the Stage 7
message header through the shared include root (-I <dest>/generated/cpp).
"""
import hashlib
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate, write_if_different, copy_if_different
from Compliance.delivery_common import (
    DELIVERY_RUNTIME, DELIVERY_RUNTIME_SRC, DELIVERY_RUNTIME_DEPS)
from Compliance.zap_common import (
    ZAP_RUNTIME, ZAP_RUNTIME_SRC, ZAP_RUNTIME_DEPS, ZAP_OUT_SUBDIR)
from Crypto.backend import transport_hardening_required

ZMQ_EXT = "_zmq.h"

# C++ transport templates (Python str.format placeholders); see templates/.
_HEADER = loadTemplate(__file__, "header.h.tmpl")
_SENDER = loadTemplate(__file__, "sender.tmpl")
_SENDER_CRITICAL = loadTemplate(__file__, "sender_critical.tmpl")
_RECEIVER = loadTemplate(__file__, "receiver.tmpl")
_STREAM = loadTemplate(__file__, "stream.tmpl")

# stream lifecycle (process.md 13.2, zmq-lifecycle epic task 1). Only a
# message carrying the `stream` modifier gets the `<name>_stream` consumer
# surface layered on its SUB socket; `event`-only and non-pub/sub messages
# are byte-identical to before. Two injection points, both empty unless the
# message has `stream`:
#   _STREAM_INCLUDES -> file scope, before `namespace harpia` (the stream
#     class needs <chrono>/<optional>, the shared config needs <cstddef>).
#   _STREAM_SHARED   -> inside the namespace, behind its own
#     HARPIA_ZMQ_STREAM_DEFINED guard (same single-definition pattern as the
#     CURVE key structs) -- StreamStatus, StreamConfig, stream_config_valid().
#     The per-message ReadResult (it carries a concrete message type) is
#     emitted by stream.tmpl in the body instead.
_STREAM_INCLUDES = (
    "#include <chrono>\n"
    "#include <cstddef>\n"
    "#include <optional>\n"
)
# NOTE: this is spliced into the header AFTER _HEADER.format(), so it must be
# final literal text -- no str.format placeholders, single braces.
_STREAM_SHARED = (
    "\n"
    "// stream lifecycle shared types (process.md 13.2). Guarded separately\n"
    "// from the per-message include guard so they stay single when several\n"
    "// *_zmq.h headers with a stream surface land in one translation unit --\n"
    "// same pattern as the CURVE key structs above.\n"
    "#ifndef HARPIA_ZMQ_STREAM_DEFINED\n"
    "#define HARPIA_ZMQ_STREAM_DEFINED\n"
    "// setup() may return INVALID; read() reports TIMEOUT instead of\n"
    "// blocking; stop() -> STOPPED; the un-stopped-connection watchdog\n"
    "// -> INVALID.\n"
    "enum class StreamStatus { OK, INVALID, TIMEOUT, STOPPED };\n"
    "\n"
    "// Passed to <name>_stream::setup(). Durations are milliseconds.\n"
    "struct StreamConfig {\n"
    "    std::string endpoint;             // tcp:// | ipc:// | inproc://\n"
    "    std::string topic;                // SUB filter (\"\" = every message)\n"
    "    int    read_timeout_ms  = 1000;   // default per-read timeout; read(ms) overrides\n"
    "    int    stop_deadline_ms = 30000;  // no successful read within this of the last\n"
    "                                      //   one -> force-kill, read() -> INVALID\n"
    "    int    reclaim_after_ms = 60000;  // dead-connection reclamation window\n"
    "                                      //   (enforced by this epic's task 2)\n"
    "    std::size_t max_records = 10000;  // per-read record cap (process.md: bound the\n"
    "                                      //   \"known maximum number of registers\")\n"
    "};\n"
    "\n"
    "// Rejects the enumerated bad-config cases: no endpoint, an endpoint with\n"
    "// no tcp:// / ipc:// / inproc:// scheme, a non-positive timeout or\n"
    "// deadline, or a zero record cap.\n"
    "inline bool stream_config_valid(const StreamConfig& c) {\n"
    "    if (c.endpoint.empty()) return false;\n"
    "    if (c.endpoint.rfind(\"tcp://\", 0) != 0 &&\n"
    "        c.endpoint.rfind(\"ipc://\", 0) != 0 &&\n"
    "        c.endpoint.rfind(\"inproc://\", 0) != 0) return false;\n"
    "    if (c.read_timeout_ms <= 0) return false;\n"
    "    if (c.stop_deadline_ms <= 0) return false;\n"
    "    if (c.max_records == 0) return false;\n"
    "    return true;\n"
    "}\n"
    "#endif  // HARPIA_ZMQ_STREAM_DEFINED\n"
)

# Injected at file scope (before `namespace harpia {`) only for a `critical`
# message type; empty for every other message, so a non-critical transport
# header is byte-identical to before this wiring landed.
_DELIVERY_INCLUDE = '#include "delivery/{}"\n'.format(DELIVERY_RUNTIME)

# CURVE (encryption-only, no ZAP allowlist) socket setup, applied before
# bind/connect. Bind side (PULL receiver / PUB publisher) only needs its own
# secret key; connect side (PUSH sender / SUB subscriber) needs the peer's
# public key plus its own keypair. See CurveServerKeys/CurveClientKeys in
# templates/header.h.tmpl. Empty key(s) -> the `if` is skipped, so a caller
# passing nothing gets today's plaintext behavior unchanged.
_CURVE_SERVER_APPLY = (
    "        if (!curve.secret_key.empty()) {\n"
    "            socket_.set(::zmq::sockopt::curve_server, true);\n"
    "            socket_.set(::zmq::sockopt::curve_secretkey, curve.secret_key);\n"
    "        }\n"
)
# Hardened profile (transport-authn "zmq-zap-allowlist"): before the socket
# becomes a CURVE_SERVER, start the per-context ZAP handler so libzmq consults
# the HARPIA_ZMQ_ALLOWLIST at the handshake -- an unknown client key is rejected
# even with valid CURVE crypto. ensure_running() is idempotent per context.
_CURVE_SERVER_APPLY_ZAP = (
    "        if (!curve.secret_key.empty()) {\n"
    "            ::harpia::zap::ensure_running(ctx);\n"
    "            socket_.set(::zmq::sockopt::curve_server, true);\n"
    "            socket_.set(::zmq::sockopt::curve_secretkey, curve.secret_key);\n"
    "        }\n"
)
# Injected at file scope for every ZMQ header under a hardened profile (every
# header has a bind-side CURVE_SERVER socket). Empty otherwise -> byte-identical.
_ZAP_INCLUDE = '#include "{}/{}"\n'.format(ZAP_OUT_SUBDIR, ZAP_RUNTIME)
_CURVE_CLIENT_APPLY = (
    "        if (!curve.server_public_key.empty()) {\n"
    "            socket_.set(::zmq::sockopt::curve_serverkey, curve.server_public_key);\n"
    "            socket_.set(::zmq::sockopt::curve_publickey, curve.public_key);\n"
    "            socket_.set(::zmq::sockopt::curve_secretkey, curve.secret_key);\n"
    "        }\n"
)


def _origin_id(md5_hash, name):
    """Deterministic compile-time sender number for a one-to-* publisher.

    Derived from the file hash + message name. (The spec also folds in a project
    hash; there is no project-level hash in the pipeline yet, so the file hash
    stands in for project+file for now.)"""
    h = hashlib.md5("{}:{}".format(md5_hash, name).encode()).hexdigest()
    return str(int(h[:15], 16))


def _is_one_to_many(mods):
    """True for a unique-publisher message (PULL/EVENT/STREAM): its sender's
    default id should stay the compile-time origin_id(). False means only
    PUSH/PUSHPULL are present -- a shared, many-to-* publisher, whose default
    id must be assigned at runtime (see runtime_origin_id() in the header
    template) so concurrent senders are distinguishable. Mirrors the same
    classification Message.py already uses for ORIGINATOR field naming."""
    return bool(mods & {"PULL", "EVENT", "STREAM"})


class ZmqAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        # transport-authn "zmq-zap-allowlist": under a hardened profile the
        # generated CURVE_SERVER sockets start a ZAP handler enforcing the
        # HARPIA_ZMQ_ALLOWLIST at the handshake. Same predicate as mTLS / RBAC,
        # never per-jurisdiction.
        self.hardened = transport_hardening_required(compliance)
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "zmq")
        # Shared, transport-agnostic delivery-guarantee runtime -- copied here
        # (mirroring the capability runtime's generated/cpp/capability/ home)
        # only when at least one `critical` transport-bearing message exists.
        self.deliveryDir = os.path.join(dest, "generated", "cpp", "delivery")
        self.zapDir = os.path.join(dest, "generated", "cpp", ZAP_OUT_SUBDIR)
        self.log = logger(outFile=None, moduleName="ZmqAdapter")

    def _curve_server_apply(self):
        return _CURVE_SERVER_APPLY_ZAP if self.hardened else _CURVE_SERVER_APPLY

    @staticmethod
    def _modifiers(msg):
        mods = getattr(msg, "access_modifiers", None) or []
        return {m[0] for m in mods}

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        critical = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            mods = self._modifiers(msg)
            push_pull = bool(mods & {"PUSH", "PULL"})
            pub_sub = bool(mods & {"EVENT", "STREAM"})
            if not (push_pull or pub_sub):
                continue
            is_critical = bool(getattr(msg, "is_critical", False))
            has_stream = "STREAM" in mods
            default_id_expr = ("origin_id()" if _is_one_to_many(mods)
                               else "runtime_origin_id()")
            header = self._render(msg, push_pull, pub_sub, default_id_expr,
                                  is_critical, has_stream)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, ZMQ_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1
            if is_critical:
                critical += 1

        if critical:
            # The delivery header pulls in harpia_audit_sink.h at the same
            # relative path, so both land in the one directory (Rule 4a
            # runtime + its F3 AuditSink dependency).
            os.makedirs(self.deliveryDir, exist_ok=True)
            copy_if_different(DELIVERY_RUNTIME_SRC,
                              os.path.join(self.deliveryDir, DELIVERY_RUNTIME))
            for dep_name, dep_src in DELIVERY_RUNTIME_DEPS:
                copy_if_different(dep_src,
                                  os.path.join(self.deliveryDir, dep_name))
            self.log.print("copied delivery-guarantee runtime into {} "
                           "({} critical transport(s))".format(
                               self.deliveryDir, critical))

        if self.hardened and written:
            # Every generated ZMQ header has a bind-side CURVE_SERVER socket, so
            # a hardened build always ships the ZAP handler (+ its F3 AuditSink
            # dependency, #included at the same relative path). Runtime cost is
            # still zero unless CURVE is actually configured on that socket.
            os.makedirs(self.zapDir, exist_ok=True)
            copy_if_different(ZAP_RUNTIME_SRC,
                              os.path.join(self.zapDir, ZAP_RUNTIME))
            for dep_name, dep_src in ZAP_RUNTIME_DEPS:
                copy_if_different(dep_src,
                                  os.path.join(self.zapDir, dep_name))
            self.log.print("copied ZAP allowlist runtime into {} "
                           "(hardened profile)".format(self.zapDir))

        if written == 0:
            self.log.print("no transport-bearing messages; no ZMQ adapters")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} ZMQ transport(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg, push_pull, pub_sub, default_id_expr,
                is_critical=False, has_stream=False):
        # A `critical` message routes its send path through the Rule 4a
        # bounded rotating queue (sender_critical.tmpl); its receiving half
        # is unchanged. Non-critical messages are byte-identical to before.
        sender_tmpl = _SENDER_CRITICAL if is_critical else _SENDER
        extra_includes = _DELIVERY_INCLUDE if is_critical else ""
        if self.hardened:
            extra_includes += _ZAP_INCLUDE
        # A `stream` message additionally gets the process.md 13.2 lifecycle
        # consumer (<name>_stream) after its SUB subscriber; `event`-only and
        # push/pull-only messages emit neither slot and stay byte-identical.
        stream_includes = _STREAM_INCLUDES if has_stream else ""
        stream_shared = _STREAM_SHARED if has_stream else ""
        cls = "::{}".format(msg.name)
        guard = "HARPIA_ZMQ_{}_{}".format(msg.name.upper(), msg.md5Hash)
        pb = "protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash)
        origin_id = _origin_id(msg.md5Hash, msg.name)
        origin_field = next((v.name for v in (msg.variables or [])
                             if v.name.startswith("ORIGINATOR")), None)
        # protobuf C++ accessors lowercase the field name
        stamp = ("        stamped.set_{}(origin_);\n".format(origin_field.lower())
                 if origin_field else "")

        body = ""
        if push_pull:
            body += sender_tmpl.format(
                comment="// push/pull: {n}_sender pushes (stamping origin), "
                        "{n}_receiver pulls.".format(n=msg.name),
                name=msg.name, role="sender", sock="push",
                connect="connect", verb="send",
                cls=cls, origin_id=origin_id, stamp=stamp,
                default_id_expr=default_id_expr,
                curve_type="CurveClientKeys", curve_apply=_CURVE_CLIENT_APPLY)
            body += _RECEIVER.format(
                name=msg.name, role="receiver", sock="pull",
                setup="socket_.bind(endpoint);", verb="recv", cls=cls,
                curve_type="CurveServerKeys", curve_apply=self._curve_server_apply())
        if pub_sub:
            body += sender_tmpl.format(
                comment="// pub/sub (streaming/event): {n}_publisher publishes "
                        "(stamping origin), {n}_subscriber receives.".format(n=msg.name),
                name=msg.name, role="publisher", sock="pub",
                connect="bind", verb="publish",
                cls=cls, origin_id=origin_id, stamp=stamp,
                default_id_expr=default_id_expr,
                curve_type="CurveServerKeys", curve_apply=self._curve_server_apply())
            body += _RECEIVER.format(
                name=msg.name, role="subscriber", sock="sub",
                setup='socket_.connect(endpoint);\n'
                      '        socket_.set(::zmq::sockopt::subscribe, "");',
                verb="receive", cls=cls,
                curve_type="CurveClientKeys", curve_apply=_CURVE_CLIENT_APPLY)
            if has_stream:
                body += _STREAM.format(
                    comment="// stream (process.md 13.2): {n}_stream is the "
                            "lifecycle consumer surface\n// layered on "
                            "{n}_subscriber's SUB socket.".format(n=msg.name),
                    name=msg.name, cls=cls,
                    curve_type="CurveClientKeys",
                    curve_apply=_CURVE_CLIENT_APPLY)
        return _HEADER.format(guard=guard, pb_header=pb, body=body,
                              extra_includes=extra_includes,
                              stream_includes=stream_includes,
                              stream_shared=stream_shared)
