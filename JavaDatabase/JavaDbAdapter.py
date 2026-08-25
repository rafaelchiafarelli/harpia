"""Session J.5 (initiatives/multi-language-targets/thread-1-java-target/
histories/DB-CRUDL-SQLITE/db-package-scaffolding.md) -- DB package
scaffolding + JDBC bind/extract primitives for the Java target.

Ships the reflection-based bind/extract runtime (runtime/JdbcBind.java, the
structural analogue of SOCI's use()/into() -- see its own header comment for
why reflection over typed accessors) and wires org.xerial:sqlite-jdbc (pure
JDBC, bundles native SQLite per-platform transparently -- no source-vendoring
needed, unlike C++'s vendored sqlite3) into build.gradle.

Out of scope here (J.6): the actual generated per-message CRUDL DAO --
JavaCrudlAdapter, in this same package, consumes JdbcBind but is a separate
class/session.
"""
import os

from logger.logger import logger
from Errors.Error import Error, Types, Classes
from util.util import copy_if_different

_RUNTIME_FILE = "JdbcBind.java"
_RUNTIME_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "runtime", _RUNTIME_FILE)
_RUNTIME_PACKAGE_DIR = ("com", "harpia", "runtime", "db")


class JavaDbAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "java", "src", "main", "java",
                                   *_RUNTIME_PACKAGE_DIR)
        self.log = logger(outFile=None, moduleName="JavaDbAdapter")

    def Process(self):
        if not self.messages:
            self.log.print("no messages to generate a DB runtime for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        os.makedirs(self.outDir, exist_ok=True)
        copy_if_different(_RUNTIME_SRC, os.path.join(self.outDir, _RUNTIME_FILE))

        self.log.print("wired the JDBC bind/extract runtime (com.harpia.runtime.db.JdbcBind) into {}".format(
            self.outDir))
        return None
