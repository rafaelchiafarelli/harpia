"""Stage 11/12 -- HTTP capability handshake (plans/message-versioning.md S5),
shared by REST and SOAP.

Generates ONE whole-project GET <base>/capabilities route (advertises every
non-enum message type this generated project declares) and ships the
hand-written client runtime (harpia_http_capability.h: negotiate()) plus the
shared transport-agnostic Dispatcher (Capability/runtime/) into the build --
same "generate the scaffolding, copy the generic runtime verbatim" split
XmlAdapter uses for harpia_xml.h.

REST and SOAP share this one mechanism rather than each getting its own:
both register routes on the same crow::SimpleApp in a real deployment (see
RestAdapter.py/SoapAdapter.py), so one shared HTTP endpoint covers both
instead of inventing a redundant SOAP-envelope-specific capability op.
"""
import os

from logger.logger import logger
from util.util import loadTemplate, write_if_different, copy_if_different
from Capability.capability_common import (
    DISPATCH_RUNTIME, DISPATCH_RUNTIME_SRC, message_type_names)

CAPABILITY_EXT = "_http.h"
RUNTIME = "harpia_http_capability.h"

_TEMPLATE = loadTemplate(__file__, "capabilities_http.h.tmpl")
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", RUNTIME)


class HttpCapabilityAdapter:
    def __init__(self, messages, dest, rootHash, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.rootHash = rootHash
        self.outDir = os.path.join(dest, "generated", "cpp", "capability")
        self.log = logger(outFile=None, moduleName="HttpCapabilityAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, RUNTIME))
        copy_if_different(DISPATCH_RUNTIME_SRC,
                          os.path.join(self.outDir, DISPATCH_RUNTIME))

        types = message_type_names(self.messages)
        typeList = ",\n            ".join('"{}"'.format(t) for t in types)
        header = _TEMPLATE.format(
            guard="HARPIA_CAPABILITY_HTTP_{}".format(self.rootHash),
            type_list=typeList,
        )
        fileName = "capabilities_{}{}".format(self.rootHash, CAPABILITY_EXT)
        write_if_different(os.path.join(self.outDir, fileName), header)

        self.log.print("generated HTTP capability advertisement ({} message "
                       "type(s)) into {}".format(len(types), self.outDir))
        return None
