"""Session J.10 (initiatives/multi-language-targets/thread-1-java-target/
histories/XML-runtime/XML-write-path.md) -- XML write path for the Java
target. (J.11 extends the same runtime file with the read path.)

Ships a single hand-written, reflection-based runtime class
(runtime/HarpiaXml.java) and generates nothing per message -- same
reasoning as JavaJsonAdapter (see its CLAUDE.md): protobuf-java's common
Message interface, walked via Descriptors.FieldDescriptor, already makes
this generic over every message type, so there is nothing per-message left
to generate. Directly comparable in shape to the C++ target's
`XmlAdapter/runtime/harpia_xml.h`, and genuinely cheaper here: `javax.xml`
(DOM) is JDK-builtin, where C++ had to vendor tinyxml2.
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import copy_if_different

_RUNTIME_FILE = "HarpiaXml.java"
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", _RUNTIME_FILE)
_RUNTIME_PACKAGE_DIR = ("com", "harpia", "runtime", "xml")


class JavaXmlAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "java", "src", "main", "java",
                                   *_RUNTIME_PACKAGE_DIR)
        self.log = logger(outFile=None, moduleName="JavaXmlAdapter")

    def Process(self):
        if not self.messages:
            self.log.print("no messages to generate an XML runtime for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        os.makedirs(self.outDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, _RUNTIME_FILE))

        self.log.print("wired the XML runtime (com.harpia.runtime.xml.HarpiaXml) into {}".format(
            self.outDir))
        return None
