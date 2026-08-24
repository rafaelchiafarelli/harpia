"""Sessions J.12/J.13/J.14 (initiatives/multi-language-targets/thread-1-
java-target/histories/REST/) -- REST routing scaffolding (J.12), CRUDL
handlers (J.13), and the acceptance gate (J.14, "nothing new") for the Java
target. Landed together -- see this session's own history files for why.

Routes on JDK-builtin com.sun.net.httpserver.HttpServer (zero dependency),
per Database/RestAdapter.py's C++ shape: GET/POST <base>/<name>,
GET/PUT/DELETE <base>/<name>/<id>. The message-agnostic mechanics (Stage 5
credential gate, content negotiation via the already-generic HarpiaJson/
HarpiaXml, collection-vs-item path splitting) live in the shared
runtime/HttpRestHelpers.java; only the DAO/message-type-specific glue is
generated per message (unlike JSON/XML, a shared class alone can't dispatch
to a per-message-typed DAO without either per-message generation or a
common Dao<T> interface this repo doesn't have -- generation is the
established pattern here, matching JavaDatabase's own DAO generation).

Deliberately reduced scope, consistent with (and a direct consequence of)
JavaDatabase's own reduction: list() is unpaginated (JavaCrudlAdapter never
built the C++ target's paginated list(out, offset, limit) overload, so
there's nothing for a ?limit=/?offset= query parameter to call here) --
flagged, not silently dropped.
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import copy_if_different, write_if_different, loadTemplate

_RUNTIME_FILE = "HttpRestHelpers.java"
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", _RUNTIME_FILE)
_RUNTIME_PACKAGE_DIR = ("com", "harpia", "runtime", "rest")

_TEMPLATE = loadTemplate(__file__, "rest.java.tmpl")


class JavaRestAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.runtimeDir = os.path.join(dest, "java", "src", "main", "java",
                                       *_RUNTIME_PACKAGE_DIR)
        self.outDir = os.path.join(dest, "java", "src", "main", "java",
                                   "com", "harpia", "generated", "rest")
        self.log = logger(outFile=None, moduleName="JavaRestAdapter")

    def Process(self):
        os.makedirs(self.runtimeDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.runtimeDir, _RUNTIME_FILE))

        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not getattr(msg, "tableName", None):
                continue
            source = _TEMPLATE.format(name=msg.name, hash=msg.md5Hash)
            fileName = "{}_rest.java".format(msg.name)
            write_if_different(os.path.join(self.outDir, fileName), source)
            written += 1

        if written == 0:
            self.log.print("no table-bearing messages to generate a Java REST binding for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} Java REST binding(s) into {}".format(written, self.outDir))
        return None
