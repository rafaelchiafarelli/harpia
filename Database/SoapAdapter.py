"""Stage 11 -- SOAP access (XML over HTTP).

For each table-bearing message, emit a header (<name>_<hash>_soap.h) that
registers a SOAP endpoint on a cpp-httplib server, backed by the CRUDL DAO and
the XML adapter (spec stage 11):

  POST <base>/<name> with a SOAP envelope whose Body holds:
    <get><id>N</id></get>            -> the <name> serialized as XML
    <set><name-xml></set>            -> create

Reuses tinyxml2 (envelope parsing) and the XML adapter; no new dependency. WSDL
generation and update/delete operations are deferred.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate

SOAP_EXT = "_soap.h"

_SOAP = loadTemplate(__file__, "soap.h.tmpl")


class SoapAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "soap")
        self.log = logger(outFile=None, moduleName="SoapAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            header = _SOAP.format(
                guard="HARPIA_SOAP_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, SOAP_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(header)
            written += 1
        self.log.print("generated {} SOAP endpoint(s) into {}".format(
            written, self.outDir))
        return None
