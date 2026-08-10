"""Stage 10 -- XML adapter generation.

Ships a generic, reflection-based XML runtime (XmlAdapter/runtime/harpia_xml.h)
into the build and emits a thin per-message wrapper header so XML has the same
shape as the JSON adapter:

  - harpia::xml::to_xml(msg)            message -> XML            (spec 10 / 9.1)
  - harpia::xml::from_xml(xml, &msg)    XML -> message            (spec 10 / 9.2)
  - harpia::xml::xsd(T::descriptor())   XSD schema                (spec 10 / 9.1)

Unlike JSON, protobuf has no built-in XML, so the runtime walks the message via
the protobuf descriptor/reflection API (handling nested messages, repeated
fields, enums and maps generically) and uses the vendored tinyxml2 for parsing.

The database-backed XML functions in the spec (9.3-9.6) are deferred until
Stage 8 (database access) exists.
"""
import os
import shutil

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate

XML_EXT = "_xml.h"
RUNTIME = "harpia_xml.h"

_WRAPPER = loadTemplate(__file__, "wrapper.h.tmpl")
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", RUNTIME)


class XmlAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "xml")
        self.log = logger(outFile=None, moduleName="XmlAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        # ship the generic runtime alongside the wrappers
        shutil.copy2(_RUNTIME_SRC, os.path.join(self.outDir, RUNTIME))

        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            header = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, XML_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(header)
            written += 1

        if written == 0:
            self.log.print("no messages to generate XML adapters for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} XML adapter(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        pbHeader = "protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash)
        guard = "HARPIA_XML_{}_{}".format(msg.name.upper(), msg.md5Hash)
        return _WRAPPER.format(guard=guard, pb_header=pbHeader, name=msg.name)
