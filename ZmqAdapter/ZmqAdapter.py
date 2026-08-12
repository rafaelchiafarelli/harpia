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
from Util.util import loadTemplate, write_if_different

ZMQ_EXT = "_zmq.h"

# C++ transport templates (Python str.format placeholders); see templates/.
_HEADER = loadTemplate(__file__, "header.h.tmpl")
_SENDER = loadTemplate(__file__, "sender.tmpl")
_RECEIVER = loadTemplate(__file__, "receiver.tmpl")


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
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "zmq")
        self.log = logger(outFile=None, moduleName="ZmqAdapter")

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
            mods = self._modifiers(msg)
            push_pull = bool(mods & {"PUSH", "PULL"})
            pub_sub = bool(mods & {"EVENT", "STREAM"})
            if not (push_pull or pub_sub):
                continue
            default_id_expr = ("origin_id()" if _is_one_to_many(mods)
                               else "runtime_origin_id()")
            header = self._render(msg, push_pull, pub_sub, default_id_expr)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, ZMQ_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1

        if written == 0:
            self.log.print("no transport-bearing messages; no ZMQ adapters")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} ZMQ transport(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg, push_pull, pub_sub, default_id_expr):
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
            body += _SENDER.format(
                comment="// push/pull: {n}_sender pushes (stamping origin), "
                        "{n}_receiver pulls.".format(n=msg.name),
                name=msg.name, role="sender", sock="push",
                connect="connect", verb="send",
                cls=cls, origin_id=origin_id, stamp=stamp,
                default_id_expr=default_id_expr)
            body += _RECEIVER.format(
                name=msg.name, role="receiver", sock="pull",
                setup="socket_.bind(endpoint);", verb="recv", cls=cls)
        if pub_sub:
            body += _SENDER.format(
                comment="// pub/sub (streaming/event): {n}_publisher publishes "
                        "(stamping origin), {n}_subscriber receives.".format(n=msg.name),
                name=msg.name, role="publisher", sock="pub",
                connect="bind", verb="publish",
                cls=cls, origin_id=origin_id, stamp=stamp,
                default_id_expr=default_id_expr)
            body += _RECEIVER.format(
                name=msg.name, role="subscriber", sock="sub",
                setup='socket_.connect(endpoint);\n'
                      '        socket_.set(::zmq::sockopt::subscribe, "");',
                verb="receive", cls=cls)
        return _HEADER.format(guard=guard, pb_header=pb, body=body)
