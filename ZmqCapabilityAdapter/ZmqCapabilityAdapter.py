"""Stage 13 -- ZMQ capability handshake (plans/message-versioning.md S5).

Generates ONE whole-project capabilities_responder (a REQ/REP pair over the
same capabilities_Request/capabilities_Response wire messages the gRPC and
HTTP slices already defined) and ships the hand-written client runtime
(harpia_zmq_capability.h: negotiate()) plus the shared transport-agnostic
Dispatcher (Capability/runtime/) into the build -- same "generate the
scaffolding, copy the generic runtime verbatim" split XmlAdapter uses for
harpia_xml.h.

ZMQ has no existing metadata channel or session concept to piggyback the
handshake onto (unlike gRPC call metadata or an HTTP request/response), so
this is its own small request/reply exchange.
"""
import os

from logger.logger import logger
from util.util import loadTemplate, write_if_different, copy_if_different
from Capability.capability_common import (
    DISPATCH_RUNTIME, DISPATCH_RUNTIME_SRC, message_type_names)

CAPABILITY_EXT = "_zmq.h"
RUNTIME = "harpia_zmq_capability.h"

_TEMPLATE = loadTemplate(__file__, "capabilities_zmq.h.tmpl")
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", RUNTIME)


class ZmqCapabilityAdapter:
    def __init__(self, messages, dest, rootHash) -> None:
        self.messages = messages
        self.dest = dest
        self.rootHash = rootHash
        self.outDir = os.path.join(dest, "generated", "cpp", "capability")
        self.log = logger(outFile=None, moduleName="ZmqCapabilityAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, RUNTIME))
        copy_if_different(DISPATCH_RUNTIME_SRC,
                          os.path.join(self.outDir, DISPATCH_RUNTIME))

        types = message_type_names(self.messages)
        typeList = ",\n        ".join('"{}"'.format(t) for t in types)
        header = _TEMPLATE.format(
            guard="HARPIA_CAPABILITY_ZMQ_{}".format(self.rootHash),
            type_list=typeList,
        )
        fileName = "capabilities_{}{}".format(self.rootHash, CAPABILITY_EXT)
        write_if_different(os.path.join(self.outDir, fileName), header)

        self.log.print("generated ZMQ capability advertisement ({} message "
                       "type(s)) into {}".format(len(types), self.outDir))
        return None
