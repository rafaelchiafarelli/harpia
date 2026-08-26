"""Stage 11 (SOAP) -- WSDL service descriptor generation.

For each table-bearing message, emit a WSDL 1.1 document (<name>_<hash>.wsdl)
describing the SOAP service the matching *_soap.h endpoint implements: the four
operations (get/set/update/delete), their request/response wrappers, a SOAP 1.1
document/literal binding, and a service port.

The message complexType lists the top-level scalar/enum fields (from the shared
Database.model, so it agrees with the schema). Nested/composed, repeated and map
fields are serialized at runtime by the XML reflection runtime and are not
expanded here. This is a static sidecar (no C++), validated by the golden tests.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different
from Database.model import analyze, type_registry

WSDL_EXT = ".wsdl"

_WSDL = loadTemplate(__file__, "wsdl.tmpl")

# column "kind" -> XSD built-in type
_XSD = {"int": "int", "int64": "long", "double": "double",
        "text": "string", "enum": "int"}


class WsdlAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "wsdl")
        self.types = type_registry(messages)
        self.log = logger(outFile=None, moduleName="WsdlAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, WSDL_EXT)
            write_if_different(os.path.join(self.outDir, fileName), self._render(msg))
            written += 1
        self.log.print("generated {} WSDL descriptor(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        columns, _ = analyze(msg, self.types)
        fields = "\n".join(
            '          <xsd:element name="{}" type="xsd:{}"/>'.format(
                c.name, _XSD.get(c.kind, "string"))
            for c in columns if c.bindable)
        return _WSDL.format(name=msg.name, hash=msg.md5Hash, fields=fields)
