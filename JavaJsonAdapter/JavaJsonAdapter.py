"""Session J.4 (initiatives/multi-language-targets/thread-1-java-target/
histories/JSON/pass-through.md) -- JSON pass-through for the Java target.

Unlike the C++ target's JsonAdapter (one generated wrapper header per
message, JsonAdapter/templates/adapter.h.tmpl), this ships a SINGLE
hand-written runtime class (runtime/HarpiaJson.java) and generates nothing
per message: protobuf-java's `Message`/`Message.Builder` are common
interfaces every message class already implements, so
`com.google.protobuf.util.JsonFormat` (the identical canonical
protobuf-JSON mapping C++/Python use, via `protobuf-java-util`) is already
generic over any message type. Generating N near-identical per-message
wrapper classes here would be pure boilerplate with no type-safety or
ergonomics benefit a plain `HarpiaJson.toJson(msg)` call doesn't already
have -- see JavaJsonAdapter/CLAUDE.md.
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import copy_if_different

_RUNTIME_FILE = "HarpiaJson.java"
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", _RUNTIME_FILE)
_RUNTIME_PACKAGE_DIR = os.path.join("com", "harpia", "runtime", "json")


class JavaJsonAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "java", "src", "main", "java",
                                   *_RUNTIME_PACKAGE_DIR.split(os.sep))
        self.log = logger(outFile=None, moduleName="JavaJsonAdapter")

    def Process(self):
        if not self.messages:
            self.log.print("no messages to generate a JSON runtime for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        os.makedirs(self.outDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, _RUNTIME_FILE))

        self.log.print("wired the JSON runtime (com.harpia.runtime.json.HarpiaJson) into {}".format(
            self.outDir))
        return None
