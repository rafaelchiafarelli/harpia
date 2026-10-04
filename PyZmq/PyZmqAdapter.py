"""python-target / py-zmq -- ZMQ transports (the Python side of
``ZmqAdapter/ZmqAdapter.py``).

Copies ``runtime/zmq.py`` as ``harpia_runtime.zmq`` and generates
``harpia_generated/zmq/<name>_<hash>_zmq.py`` for every message the C++
adapter emits a header for (PUSH/PULL → sender/receiver, EVENT/STREAM →
publisher/subscriber). The origin id and the one-to-many rule are imported
from ``ZmqAdapter.ZmqAdapter``, not re-derived.
"""
import os

from Compliance.audit_common import PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC
from Compliance.delivery_common import PY_DELIVERY_MODULE, PY_DELIVERY_RUNTIME_SRC
from Crypto.backend import transport_hardening_required
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different
from ZmqAdapter.ZmqAdapter import ZmqAdapter, _is_one_to_many, _origin_id

_TEMPLATE = loadTemplate(__file__, "zmq.py.tmpl")
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
ZMQ_MODULE = "harpia_runtime.zmq"
ZAP_MODULE = "harpia_runtime.zap"
ZMQ_DELIVERY_MODULE = "harpia_runtime.zmq_delivery"
ZMQ_STREAM_MODULE = "harpia_runtime.zmq_stream"

# a `stream` type's lifecycle consumer (py-zmq task 4)
_STREAM = '''

class {name}_stream(Stream[{name}]):
    """The ``stream`` lifecycle consumer of ``{name}`` (a timed, stoppable SUB
    read with watchdog + dead-connection reclamation; see
    :mod:`harpia_runtime.zmq_stream`)::

        from harpia_runtime.zmq_stream import StreamConfig, StreamStatus
        s = {name}_stream(ctx)
        if s.setup(StreamConfig("tcp://host:port")) is StreamStatus.OK:
            result = s.read()  # result.status / result.msg
        s.stop()
    """

    MESSAGE = {name}
'''
ZMQ_EXT = "_zmq.py"

_SENDER = '''

def new_{role}(ctx: zmq.Context[Any], endpoint: str,
{pad}origin: str | None = None,
{pad}curve: {curve_type} | None = None) -> Sender[{name}]:
    """A {sock} socket that {verb} ``{name}`` messages ({connect}s ``endpoint``).

    ``origin`` overrides the stamped id (default: {default_doc}).
    ``curve`` enables CURVE encryption (omit for plaintext).{zap_doc}
    """
    return Sender(ctx, endpoint, {default_expr} if origin is None else origin,
                  {pub}curve=curve{zap})
'''

# a `critical` type's sender/publisher: queued (py-zmq task 3)
_SENDER_CRITICAL = '''

def new_{role}(ctx: zmq.Context[Any], endpoint: str,
{pad}origin: str | None = None,
{pad}curve: {curve_type} | None = None,
{pad}queue_capacity: int = 128,
{pad}audit_sink: AuditSink | None = None) -> QueuedSender[{name}]:
    """A {sock} socket that queues ``{name}`` messages ({connect}s ``endpoint``).

    ``{name}`` is ``critical``: ``{verb_base}()`` stamps a CRC + sequence
    envelope into a bounded queue of ``queue_capacity`` (an overflow rotates
    the oldest out with a ``queue_rotated`` record to ``audit_sink``) and
    ``flush()`` puts the payloads on the wire, oldest first.

    ``origin`` overrides the stamped id (default: {default_doc}).
    ``curve`` enables CURVE encryption (omit for plaintext).{zap_doc}
    """
    return QueuedSender(ctx, endpoint, {default_expr} if origin is None else origin,
                        {pub}curve=curve{zap}, queue_capacity=queue_capacity,
                        audit_sink=audit_sink, subject={name_lit})
'''

_RECEIVER = '''

def new_{role}(ctx: zmq.Context[Any], endpoint: str,
{pad}curve: {curve_type} | None = None) -> Receiver[{name}]:
    """A {sock} socket receiving ``{name}`` messages ({connect}s ``endpoint``).

    ``curve`` enables CURVE encryption (omit for plaintext).{zap_doc}
    """
    return Receiver(ctx, endpoint, {name}, {sub}curve=curve{zap})
'''


class PyZmqAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "harpia_generated", "zmq")
        # hardened profile: bind-side CURVE sockets enforce the ZAP allowlist
        self.hardened = transport_hardening_required(compliance)
        self.log = logger(outFile=None, moduleName="PyZmqAdapter")

    def _transports(self):
        out = []
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            mods = ZmqAdapter._modifiers(msg)
            push_pull = bool(mods & {"PUSH", "PULL"})
            pub_sub = bool(mods & {"EVENT", "STREAM"})
            if push_pull or pub_sub:
                out.append((msg, mods, push_pull, pub_sub))
        return out

    def Process(self):
        transports = self._transports()
        if not transports:
            return None
        copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, "zmq.py"), ZMQ_MODULE)
        if self.hardened:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, "zap.py"), ZAP_MODULE)
            copy_runtime_module(self.dest, PY_AUDIT_SINK_RUNTIME_SRC, PY_AUDIT_SINK_MODULE)
        if any("STREAM" in mods for _, mods, *_ in transports):
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, "zmq_stream.py"),
                                ZMQ_STREAM_MODULE)
        if any(getattr(m, "is_critical", False) for m, *_ in transports):
            for module, src in ((PY_DELIVERY_MODULE, PY_DELIVERY_RUNTIME_SRC),
                                (ZMQ_DELIVERY_MODULE,
                                 os.path.join(_RUNTIME_DIR, "zmq_delivery.py")),
                                (PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC)):
                copy_runtime_module(self.dest, src, module)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "__init__.py"),
                           '"""Generated ZMQ transports, one module per '
                           'transport-bearing message."""\n')
        for msg, mods, push_pull, pub_sub in transports:
            write_if_different(os.path.join(
                self.outDir, "{}_{}{}".format(msg.name, msg.md5Hash, ZMQ_EXT)),
                self._render(msg, mods, push_pull, pub_sub))
        self.log.print("generated {} ZMQ transport(s) into {}".format(
            len(transports), self.outDir))
        return None

    def _render(self, msg, mods, push_pull, pub_sub):
        one_to_many = _is_one_to_many(mods)
        default_expr = "ORIGIN_ID" if one_to_many else "runtime_origin_id()"
        default_doc = ("``ORIGIN_ID``, this one-to-* type's compile-time id"
                       if one_to_many else
                       "a fresh ``runtime_origin_id()`` per sender, since many "
                       "senders share this type")
        name = msg.name
        factories, roles = "", []

        zap_doc = ("\n    Hardened profile: CURVE also enforces the ``HARPIA_ZMQ_ALLOWLIST``\n"
                   "    client-key allowlist (:mod:`harpia_runtime.zap`).")

        def bind_side(bind):
            hardened = bind and self.hardened
            return dict(curve_type="CurveServerKeys" if bind else "CurveClientKeys",
                        zap=", zap=True" if hardened else "",
                        zap_doc=zap_doc if hardened else "")

        critical = bool(getattr(msg, "is_critical", False))

        def sender(role, sock, verb, connect, pub):
            pad = " " * len("def new_{}(".format(role))
            tmpl = _SENDER_CRITICAL if critical else _SENDER
            return tmpl.format(role=role, name=name, sock=sock, verb=verb,
                                  verb_base="publish" if pub else "send",
                                  name_lit=repr(name),
                                  connect=connect, pad=pad, default_doc=default_doc,
                                  default_expr=default_expr,
                                  pub="pub=True, " if pub else "", **bind_side(pub))

        def receiver(role, sock, connect, sub):
            pad = " " * len("def new_{}(".format(role))
            return _RECEIVER.format(role=role, name=name, sock=sock, connect=connect,
                                    pad=pad, sub="sub=True, " if sub else "",
                                    **bind_side(not sub))

        if push_pull:
            factories += sender("sender", "PUSH", "sends", "connect", False)
            factories += receiver("receiver", "PULL", "bind", False)
            roles += ["``new_sender`` (PUSH)", "``new_receiver`` (PULL)"]
        if pub_sub:
            factories += sender("publisher", "PUB", "publishes", "bind", True)
            factories += receiver("subscriber", "SUB", "connect", True)
            roles += ["``new_publisher`` (PUB)", "``new_subscriber`` (SUB)"]
            if "STREAM" in mods:
                factories += _STREAM.format(name=name)
                roles.append("``{}_stream`` (stream lifecycle)".format(name))
        curve_types = (["CurveClientKeys", "CurveServerKeys"])
        imports = curve_types + ["Receiver"] + ([] if critical else ["Sender"]) + (
            [] if one_to_many else ["runtime_origin_id"])
        origin_doc = ("One-to-* type: every sender stamps ``ORIGIN_ID`` by default."
                      if one_to_many else
                      "Many-to-* type: each sender stamps its own runtime id by default.")
        extra_imports = ""
        if critical:
            extra_imports = ("from harpia_runtime.compliance.audit_sink import AuditSink\n")
            post_imports = ("from harpia_runtime.zmq_delivery import QueuedSender\n")
        else:
            post_imports = ""
        if "STREAM" in mods:
            post_imports += "from harpia_runtime.zmq_stream import Stream\n"
        return _TEMPLATE.format(name=name, hash=msg.md5Hash, roles=", ".join(roles),
                                extra_imports=extra_imports, post_imports=post_imports,
                                origin_doc=origin_doc, runtime_imports="".join("    {},\n".format(i) for i in imports).rstrip("\n"),
                                origin_id_lit=repr(_origin_id(msg.md5Hash, name)),
                                factories=factories.rstrip("\n"))
