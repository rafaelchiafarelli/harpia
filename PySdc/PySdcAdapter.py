"""python-target / py-discovery -- WS-Discovery responder for the Python SOAP
endpoints (the Python side of ``SdcAdapter``).

Copies ``runtime/wsdiscovery.py`` as ``harpia_runtime.wsdiscovery`` and
generates ``harpia_generated/sdc/<name>_<hash>_sdc.py`` per table-bearing
message (``SdcAdapter``'s filter). The scope prefix, the generic device type,
the project name and the UUID5 endpoint reference are ``SdcAdapter``'s,
imported -- never re-derived -- so a C++ and a Python build of one schema
advertise identical descriptors.
"""
import os

from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from SdcAdapter.SdcAdapter import (
    GENERIC_DEVICE_TYPE,
    SCOPE_PREFIX,
    _endpoint_reference,
    _project_name,
)
from Util.util import loadTemplate, write_if_different

_TEMPLATE = loadTemplate(__file__, "sdc.py.tmpl")
_RUNTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime",
                        "wsdiscovery.py")
WSDISCOVERY_MODULE = "harpia_runtime.wsdiscovery"
SDC_EXT = "_sdc.py"


class PySdcAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "harpia_generated", "sdc")
        self.log = logger(outFile=None, moduleName="PySdcAdapter")

    def Process(self):
        tables = [m for m in self.messages
                  if not getattr(m, "isEnum", False) and m.tableName]
        if not tables:
            return None
        copy_runtime_module(self.dest, _RUNTIME, WSDISCOVERY_MODULE)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "__init__.py"),
                           '"""Generated WS-Discovery descriptors, one per SOAP endpoint."""\n')
        project = _project_name(self.compliance)
        for msg in tables:
            write_if_different(
                os.path.join(self.outDir, "{}_{}{}".format(msg.name, msg.md5Hash, SDC_EXT)),
                _TEMPLATE.format(
                    name=msg.name, hash=msg.md5Hash,
                    epr_lit=repr(_endpoint_reference(project, msg.name, msg.md5Hash)),
                    device_type_lit=repr(GENERIC_DEVICE_TYPE),
                    scope_lit=repr("{}/{}/{}".format(SCOPE_PREFIX, project, msg.name))))
        self.log.print("generated {} WS-Discovery descriptor(s) into {}".format(
            len(tables), self.outDir))
        return None
