"""Stage 11 -- SOAP access (XML over HTTP).

For each table-bearing message, emit a header (<name>_<hash>_soap.h) that
registers a SOAP endpoint on a Crow server (crow::SimpleApp), backed by the CRUDL
DAO and the XML adapter (spec stage 11):

  POST <base>/<name> with a SOAP envelope whose Body holds:
    <get><id>N</id></get>            -> the <name> serialized as XML
    <set><name-xml></set>            -> create
    <update><name-xml></update>      -> update
    <delete><id>N</id></delete>      -> delete

Reuses tinyxml2 (envelope parsing) and the XML adapter; no new dependency. WSDL
generation is deferred.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different, copy_if_different
from Database.auth_gate import soap_auth_fills
from Crypto.backend import transport_hardening_required

SOAP_EXT = "_soap.h"

# The pure envelope-parse seam the generated endpoint #includes and the fuzz
# harness targets (static-fuzz-ci task 4a). Shipped verbatim alongside the
# per-message wrappers -- the XmlAdapter/harpia_xml.h pattern.
SOAP_RUNTIME = "harpia_soap.h"
_SOAP_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "SoapAdapter", "runtime", SOAP_RUNTIME)

_SOAP = loadTemplate(__file__, "soap.h.tmpl")


class SoapAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "soap")
        self.log = logger(outFile=None, moduleName="SoapAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        # ship the hand-written envelope-parse seam alongside the wrappers
        # (static-fuzz-ci task 4a) -- the generated headers #include it.
        copy_if_different(_SOAP_RUNTIME_SRC,
                          os.path.join(self.outDir, SOAP_RUNTIME))
        # transport-authn task 4: same gen-time RBAC-vs-flat choice as REST/gRPC
        # (RestAdapter copies harpia_rbac.h into the shared generated/cpp/http/
        # dir this endpoint #includes from, so nothing to copy here).
        rbac = transport_hardening_required(self.compliance)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            header = _SOAP.format(
                guard="HARPIA_SOAP_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
                **soap_auth_fills(msg.name, msg.md5Hash, rbac),
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, SOAP_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1
        self.log.print("generated {} SOAP endpoint(s) into {}".format(
            written, self.outDir))
        return None
