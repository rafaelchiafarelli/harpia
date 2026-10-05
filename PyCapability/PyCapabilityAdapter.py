"""python-target / py-versioning -- capability handshake (the Python side of
``GrpcCapabilityAdapter`` / ``HttpCapabilityAdapter`` /
``ZmqCapabilityAdapter``, message-versioning S5).

Copies the transport-agnostic ``Dispatcher`` and the gRPC ``negotiate()``
runtime under ``harpia_runtime.capability`` and generates the whole-project
``harpia_generated/capability/capabilities_<roothash>_grpc.py`` servicer
(registered by the generated ``GrpcServer``). The advertised set is
``Capability.capability_common.message_type_names`` -- imported, not
re-derived.
"""
import os

from Capability.capability_common import message_type_names
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_GRPC = loadTemplate(__file__, "capabilities_grpc.py.tmpl")
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
#: (source file under runtime/, destination module)
RUNTIMES = (
    ("dispatch.py", "harpia_runtime.capability.dispatch"),
    ("grpc.py", "harpia_runtime.capability.grpc"),
)
GRPC_EXT = "_grpc.py"


def grpc_module(root_hash):
    """The generated servicer's module name (``capabilities_<roothash>_grpc``)."""
    return "capabilities_{}{}".format(root_hash, GRPC_EXT[:-3])


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
        write_if_different(
            os.path.join(self.outDir, grpc_module(self.rootHash) + ".py"),
            _GRPC.format(root_hash=self.rootHash,
                         type_list="".join("    {!r},\n".format(t) for t in types).rstrip("\n")))
        self.log.print("generated capability advertisement ({} type(s)) into {}".format(
            len(types), self.outDir))
        return None
