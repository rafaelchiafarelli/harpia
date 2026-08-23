"""Stage 13 -- gRPC capability handshake (plans/message-versioning.md S5).

Generates the server-side capabilities_service implementation (advertises
every non-enum message type this generated project declares) and ships the
hand-written client runtime (harpia_capability.h: negotiate()) plus the
shared transport-agnostic Dispatcher (Capability/runtime/) into the build,
the same "generate the scaffolding, copy the generic runtime verbatim" split
XmlAdapter uses for harpia_xml.h.

Unlike every other Stage 13 adapter this is a WHOLE-PROJECT artifact, not
per-message: the capability SET is a property of the generated peer as a
whole (does this peer's code know about type X at all), not of any one
message, so there is exactly one capabilities_<roothash>_grpc.h regardless
of how many messages the schema declares.
"""
import os

from logger.logger import logger
from util.util import loadTemplate, write_if_different, copy_if_different
from Capability.capability_common import (
    DISPATCH_RUNTIME, DISPATCH_RUNTIME_SRC, message_type_names)

CAPABILITY_EXT = "_grpc.h"
RUNTIME = "harpia_capability.h"

_TEMPLATE = loadTemplate(__file__, "capabilities_service.h.tmpl")
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", RUNTIME)


class GrpcCapabilityAdapter:
    def __init__(self, messages, dest, rootHash) -> None:
        self.messages = messages
        self.dest = dest
        self.rootHash = rootHash
        self.outDir = os.path.join(dest, "generated", "cpp", "capability")
        self.log = logger(outFile=None, moduleName="GrpcCapabilityAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        # ship the generic client runtime + shared dispatch runtime
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, RUNTIME))
        copy_if_different(DISPATCH_RUNTIME_SRC,
                          os.path.join(self.outDir, DISPATCH_RUNTIME))

        types = message_type_names(self.messages)
        typeList = ",\n        ".join('"{}"'.format(t) for t in types)
        header = _TEMPLATE.format(
            guard="HARPIA_CAPABILITY_{}".format(self.rootHash),
            type_list=typeList,
        )
        fileName = "capabilities_{}{}".format(self.rootHash, CAPABILITY_EXT)
        write_if_different(os.path.join(self.outDir, fileName), header)

        self.log.print("generated capability advertisement ({} message "
                       "type(s)) into {}".format(len(types), self.outDir))
        return None
