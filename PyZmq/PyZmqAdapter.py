"""python-target / py-zmq -- ZMQ transports (the Python side of
``ZmqAdapter/ZmqAdapter.py``).

Copies ``runtime/zmq.py`` as ``harpia_runtime.zmq`` and generates
``harpia_generated/zmq/<name>_<hash>_zmq.py`` for every message the C++
adapter emits a header for (PUSH/PULL → sender/receiver, EVENT/STREAM →
publisher/subscriber). The origin id and the one-to-many rule are imported
from ``ZmqAdapter.ZmqAdapter``, not re-derived.
"""
import os

from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different
from ZmqAdapter.ZmqAdapter import ZmqAdapter, _is_one_to_many, _origin_id

_TEMPLATE = loadTemplate(__file__, "zmq.py.tmpl")
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
ZMQ_MODULE = "harpia_runtime.zmq"
ZMQ_EXT = "_zmq.py"

_SENDER = '''

def new_{role}(ctx: zmq.Context[Any], endpoint: str,
{pad}origin: str | None = None) -> Sender[{name}]:
    """A {sock} socket that {verb}s ``{name}`` messages ({connect}s ``endpoint``).

    ``origin`` overrides the stamped id (default: {default_doc}).
    """
    return Sender(ctx, endpoint, {default_expr} if origin is None else origin{pub})
'''

_RECEIVER = '''

def new_{role}(ctx: zmq.Context[Any], endpoint: str) -> Receiver[{name}]:
    """A {sock} socket receiving ``{name}`` messages ({connect}s ``endpoint``)."""
    return Receiver(ctx, endpoint, {name}{sub})
'''


class PyZmqAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "harpia_generated", "zmq")
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

        def sender(role, sock, verb, connect, pub):
            pad = " " * len("def new_{}(".format(role))
            return _SENDER.format(role=role, name=name, sock=sock, verb=verb,
                                  connect=connect, pad=pad, default_doc=default_doc,
                                  default_expr=default_expr,
                                  pub=", pub=True" if pub else "")

        if push_pull:
            factories += sender("sender", "PUSH", "send", "connect", False)
            factories += _RECEIVER.format(role="receiver", name=name, sock="PULL",
                                          connect="bind", sub="")
            roles += ["``new_sender`` (PUSH)", "``new_receiver`` (PULL)"]
        if pub_sub:
            factories += sender("publisher", "PUB", "publish", "bind", True)
            factories += _RECEIVER.format(role="subscriber", name=name, sock="SUB",
                                          connect="connect", sub=", sub=True")
            roles += ["``new_publisher`` (PUB)", "``new_subscriber`` (SUB)"]
        imports = ["Receiver", "Sender"] + ([] if one_to_many else ["runtime_origin_id"])
        origin_doc = ("One-to-* type: every sender stamps ``ORIGIN_ID`` by default."
                      if one_to_many else
                      "Many-to-* type: each sender stamps its own runtime id by default.")
        return _TEMPLATE.format(name=name, hash=msg.md5Hash, roles=", ".join(roles),
                                origin_doc=origin_doc, runtime_imports=", ".join(imports),
                                origin_id_lit=repr(_origin_id(msg.md5Hash, name)),
                                factories=factories.rstrip("\n"))
