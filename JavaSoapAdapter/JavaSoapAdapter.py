"""Sessions J.15/J.16 (initiatives/multi-language-targets/thread-1-java-
target/histories/SOAP/) -- SOAP envelope parsing (J.15) and the acceptance
gate (J.16, "nothing new" per its own history file) for the Java target.
Landed together.

Minimal SOAP-over-HTTP access, backed by JavaDatabase's CRUDL DAOs and the
J.10/J.11 XML runtime -- NOT a real SOAP/WS-* stack, same hand-rolled
envelope get/set/update/delete framing Database/SoapAdapter.py already
uses for the C++ target (Java's own SOAP story, JAX-WS removed from the
JDK since 11, doesn't matter here for exactly that reason -- no extra
dependency needed either way). Message-agnostic envelope parsing lives in
the shared runtime/SoapHelpers.java; only the DAO/message-type-specific
glue is generated per message, same split as JavaRestAdapter.
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import copy_if_different, write_if_different, loadTemplate

_RUNTIME_FILE = "SoapHelpers.java"
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", _RUNTIME_FILE)
_RUNTIME_PACKAGE_DIR = ("com", "harpia", "runtime", "soap")

_TEMPLATE = loadTemplate(__file__, "soap.java.tmpl")


class JavaSoapAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.runtimeDir = os.path.join(dest, "java", "src", "main", "java",
                                       *_RUNTIME_PACKAGE_DIR)
        self.outDir = os.path.join(dest, "java", "src", "main", "java",
                                   "com", "harpia", "generated", "soap")
        self.log = logger(outFile=None, moduleName="JavaSoapAdapter")

    def Process(self):
        os.makedirs(self.runtimeDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.runtimeDir, _RUNTIME_FILE))

        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not getattr(msg, "tableName", None):
                continue
            source = _TEMPLATE.format(name=msg.name, hash=msg.md5Hash)
            fileName = "{}_soap.java".format(msg.name)
            write_if_different(os.path.join(self.outDir, fileName), source)
            written += 1

        if written == 0:
            self.log.print("no table-bearing messages to generate a Java SOAP endpoint for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} Java SOAP endpoint(s) into {}".format(written, self.outDir))
        return None
