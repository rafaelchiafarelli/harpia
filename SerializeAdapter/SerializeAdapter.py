"""Stage 10 -- unified serialization façade (Track F / Session F.2).

Closes out the JSON/XML/YAML `toString` triad through one shared path. Ships a
single runtime header (SerializeAdapter/runtime/harpia_serialize.h) that
dispatches `harpia::serialize::to_string(msg, Format)` /
`from_string(text, &msg, Format)` to the existing per-format engines
(protobuf's JSON util, harpia_xml.h, harpia_yaml.h) -- so JSON and XML output
stay byte-for-byte what they were, and a later `phi` redaction pass (F.3) has
one place to hook instead of three.

Emits one thin per-message wrapper `<name>_<hash>_serialize.h`, same shape as
the JSON/XML/YAML adapters.
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate, write_if_different, copy_if_different

SERIALIZE_EXT = "_serialize.h"
RUNTIME = "harpia_serialize.h"

_WRAPPER = loadTemplate(__file__, "wrapper.h.tmpl")
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", RUNTIME)


class SerializeAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "serialize")
        self.log = logger(outFile=None, moduleName="SerializeAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, RUNTIME))

        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            header = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, SERIALIZE_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1

        if written == 0:
            self.log.print("no messages to generate serialization wrappers for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} unified serialization wrapper(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        pbHeader = "protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash)
        guard = "HARPIA_SERIALIZE_{}_{}".format(msg.name.upper(), msg.md5Hash)
        return _WRAPPER.format(guard=guard, pb_header=pbHeader, name=msg.name)
