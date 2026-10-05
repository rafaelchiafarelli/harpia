"""python-target / py-versioning -- capability handshake (the Python side of
``GrpcCapabilityAdapter`` / ``HttpCapabilityAdapter`` /
``ZmqCapabilityAdapter``, message-versioning S5).

Copies the transport-agnostic ``Dispatcher`` and the gRPC / HTTP / ZMQ
``negotiate()`` runtimes under ``harpia_runtime.capability`` and generates the
whole-project ``harpia_generated/capability/capabilities_<roothash>_{grpc,
http,zmq}.py`` advertisements (the gRPC servicer is registered by the
generated ``GrpcServer``, the HTTP route by ``HttpServer``). The advertised set is
``Capability.capability_common.message_type_names`` -- imported, not
re-derived.
"""
import os

from Capability.capability_common import message_type_names
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_GRPC = loadTemplate(__file__, "capabilities_grpc.py.tmpl")
_HTTP = loadTemplate(__file__, "capabilities_http.py.tmpl")
_ZMQ = loadTemplate(__file__, "capabilities_zmq.py.tmpl")
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
#: (source file under runtime/, destination module)
RUNTIMES = (
    ("dispatch.py", "harpia_runtime.capability.dispatch"),
    ("grpc.py", "harpia_runtime.capability.grpc"),
    ("http.py", "harpia_runtime.capability.http"),
    ("zmq.py", "harpia_runtime.capability.zmq"),
)


def grpc_module(root_hash):
    """The generated servicer's module name (``capabilities_<roothash>_grpc``)."""
    return "capabilities_{}_grpc".format(root_hash)


def has_http(messages):
    """True when ``PyHttpAdapter`` emits an ``HttpServer`` (a table-bearing
    message exists), which the HTTP capability route lives on."""
    return any(not getattr(m, "isEnum", False) and getattr(m, "tableName", None)
               for m in messages)


def http_module(root_hash):
    """The generated HTTP route's module name (``capabilities_<roothash>_http``)."""
    return "capabilities_{}_http".format(root_hash)


class PyCapabilityAdapter:
    def __init__(self, messages, dest, rootHash, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.rootHash = rootHash
        self.outDir = os.path.join(dest, "python", "harpia_generated", "capability")
        self.log = logger(outFile=None, moduleName="PyCapabilityAdapter")

    def Process(self):
        for src, module in RUNTIMES:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, src), module)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "__init__.py"),
                           '"""Generated capability advertisements (whole project)."""\n')
        types = message_type_names(self.messages)
        type_list = "".join("    {!r},\n".format(t) for t in types).rstrip("\n")
        outputs = [(_GRPC, grpc_module(self.rootHash)),
                   (_ZMQ, "capabilities_{}_zmq".format(self.rootHash))]
        if has_http(self.messages):  # the route needs harpia_runtime.http (PyHttp)
            outputs.append((_HTTP, http_module(self.rootHash)))
        for tmpl, module in outputs:
            write_if_different(os.path.join(self.outDir, module + ".py"),
                               tmpl.format(root_hash=self.rootHash, type_list=type_list))
        self.log.print("generated capability advertisement ({} type(s)) into {}".format(
            len(types), self.outDir))
        return None
