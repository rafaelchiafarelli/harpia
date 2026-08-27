"""Stage 10 -- YAML adapter generation (Track F / Session F.1).

Ships a generic, reflection-based YAML runtime (YamlAdapter/runtime/harpia_yaml.h)
into the build and emits a thin per-message wrapper header so YAML has the same
shape as the JSON and XML adapters:

  - harpia::yaml::to_yaml(msg)          message -> YAML   (block style, 2-space)
  - harpia::yaml::from_yaml(yaml, &msg) YAML -> message

Like XmlAdapter (protobuf has no built-in YAML), the runtime walks the message
via the protobuf descriptor/reflection API, so nested messages, repeated
fields, enums and maps are handled generically with no per-field codegen.

F.1 is output-parity only -- no `phi` redaction yet (that is F.3), and the
JSON/XML/YAML `toString` paths are still three separate code paths (unified in
F.2).
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate, write_if_different, copy_if_different

YAML_EXT = "_yaml.h"
RUNTIME = "harpia_yaml.h"

_WRAPPER = loadTemplate(__file__, "wrapper.h.tmpl")
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", RUNTIME)


class YamlAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "yaml")
        self.log = logger(outFile=None, moduleName="YamlAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        # ship the generic runtime alongside the wrappers
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, RUNTIME))

        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            header = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, YAML_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1

        if written == 0:
            self.log.print("no messages to generate YAML adapters for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} YAML adapter(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        pbHeader = "protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash)
        guard = "HARPIA_YAML_{}_{}".format(msg.name.upper(), msg.md5Hash)
        return _WRAPPER.format(guard=guard, pb_header=pbHeader, name=msg.name)
