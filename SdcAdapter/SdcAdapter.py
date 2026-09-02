"""Stage 11 (SDC / WS-Discovery) -- zero-config discovery for the existing SOAP
endpoint (sdc-biceps epic, task 2).

IEEE 11073 SDC's transport binding (MDPWS) is SOAP-over-HTTP with WS-Discovery
for peer discovery. Harpia already emits the SOAP endpoint (Stage 11,
`Database/SoapAdapter.py`); this adapter adds the missing piece -- a
WS-Discovery probe/resolve responder -- **alongside** it. `SoapAdapter.py` /
`WsdlAdapter.py` are read as precedent only, never modified; nothing here
replaces the SOAP surface, it only advertises it.

Scope this pass is deliberately small (the epic is a scoping/design
deliverable -- the full BICEPS MDS/VMD/Channel participant model is a
follow-on epic):

  - **No new `.harpia` grammar.** A discovered participant advertises a
    *fixed generic* DPWS device type (`dpws:Device`) and a Harpia-namespaced
    scope URI minted per project + message
    (`https://harpia.dev/sdc/scope/<project>/<message>`, project baked in so
    two projects can't collide -- same discipline as the FHIR
    `identifier.system` scheme). Nothing is inferred from a field name/type.
  - Emitted per table-bearing message (same filter as `SoapAdapter`, since
    discovery points at that message's SOAP endpoint):
        generated/cpp/sdc/<name>_<hash>_sdc.h     participant descriptor +
                                                  register_<name>_wsdiscovery()
        generated/cpp/sdc/<name>_<hash>.wsdd.xml  static ProbeMatch sidecar
                                                  (golden-tested, no C++)
  - Emitted once when the schema has any table-bearing message:
        generated/cpp/sdc/harpia_wsdiscovery.h    hand-written responder
                                                  runtime (copied verbatim,
                                                  same as the capability
                                                  dispatch runtime)

Wired into `main.py` immediately after `WsdlAdapter`.
"""
import os
import uuid

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate, write_if_different, copy_if_different

SDC_EXT = "_sdc.h"
DESCRIPTOR_EXT = ".wsdd.xml"

#: Hand-written responder runtime, copied next to the generated headers the
#: same way `Capability/runtime/harpia_capability_dispatch.h` is.
WSDISCOVERY_RUNTIME = "harpia_wsdiscovery.h"
WSDISCOVERY_RUNTIME_SRC = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "runtime", WSDISCOVERY_RUNTIME)

#: Fixed generic device type advertised in every ProbeMatch this pass -- a
#: single DPWS QName, no per-message or grammar-driven type. Its namespace is
#: hard-coded in the runtime's Types element.
GENERIC_DEVICE_TYPE = "dpws:Device"

#: Per-project scope URI prefix. `<project>` comes from the F1
#: ComplianceContext (`project.harpia.yaml` `project:` key, default
#: "default"); `<message>` is appended per endpoint.
SCOPE_PREFIX = "https://harpia.dev/sdc/scope"

#: Fixed UUID5 namespace for minting a per-endpoint `urn:uuid:` reference.
#: Constant so the reference is deterministic (stable golden) yet a
#: spec-valid RFC-4122 v5 UUID rather than a raw hash.
_EPR_NAMESPACE = uuid.UUID("6ba7b814-9dad-11d1-80b4-00c04fd430c8")

_SDC_HEADER = loadTemplate(__file__, "sdc.h.tmpl")
_DESCRIPTOR = loadTemplate(__file__, "descriptor.xml.tmpl")


def _project_name(compliance):
    """The registry/owner project name (F1). Falls back to "default" exactly
    as `ComplianceContext` itself does when `project.harpia.yaml` omits it."""
    return getattr(compliance, "project", None) or "default"


def _endpoint_reference(project, name, md5_hash):
    """A stable `urn:uuid:` endpoint reference, deterministic from
    project + message + file hash so the golden sidecar never churns (a
    spec-valid RFC-4122 v5 UUID). A real deployment may override it;
    discovery only needs it stable within a generated build."""
    return "urn:uuid:" + str(uuid.uuid5(
        _EPR_NAMESPACE, "{}:{}:{}".format(project, name, md5_hash)))


class SdcAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "sdc")
        self.log = logger(outFile=None, moduleName="SdcAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        project = _project_name(self.compliance)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            scope = "{}/{}/{}".format(SCOPE_PREFIX, project, msg.name)
            epr = _endpoint_reference(project, msg.name, msg.md5Hash)

            header = _SDC_HEADER.format(
                guard="HARPIA_SDC_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                runtime=WSDISCOVERY_RUNTIME,
                epr=epr,
                device_type=GENERIC_DEVICE_TYPE,
                scope=scope,
            )
            write_if_different(
                os.path.join(self.outDir,
                             "{}_{}{}".format(msg.name, msg.md5Hash, SDC_EXT)),
                header)

            descriptor = _DESCRIPTOR.format(
                name=msg.name, epr=epr,
                device_type=GENERIC_DEVICE_TYPE, scope=scope)
            write_if_different(
                os.path.join(self.outDir, "{}_{}{}".format(
                    msg.name, msg.md5Hash, DESCRIPTOR_EXT)),
                descriptor)
            written += 1

        if written == 0:
            self.log.print("no table-bearing messages; no WS-Discovery responder")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        copy_if_different(WSDISCOVERY_RUNTIME_SRC,
                          os.path.join(self.outDir, WSDISCOVERY_RUNTIME))
        self.log.print(
            "generated {} WS-Discovery participant descriptor(s) into {}".format(
                written, self.outDir))
        return None
