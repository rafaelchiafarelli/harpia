"""process-artifacts epic -- SBOM emission (task 1 of the epic).

Stands up the `ComplianceReport/` module and makes it emit a CycloneDX 1.5
JSON SBOM for the *generated project* (not the generator's own toolchain):
`<dest>/generated/ComplianceReport/bom.json`.

A per-generation module, wired into `main.py` + `UnitTests/run_pipeline.py`
after the last adapter, same shape as `SerializeAdapter` / `Doxygen`.

Component set: `ComplianceReport/components.py` (a declared manifest, not
scraped). Vendored libs resolve their version from
`third_party/<dir>/VENDORED.md`; environment libs (protobuf/grpc/libzmq)
from the build toolchain; `"unknown"` when unresolvable -- never omitted.
The selected crypto backend is read from
`<dest>/build_metadata/crypto_backend.json` (F5, already emitted by the
pipeline).

`jurisdiction[]` is recorded as an inert `metadata.property` only (master
plan Section 0a) -- SBOM content never branches on it. Only the
jurisdiction-template-selection task (task 3) consumes it.

Schema-structural validation lives in `UnitTests/test_sbom_emission.py`
against the vendored `ComplianceReport/schema/bom-1.5.schema.json`; there is
no `jsonschema` runtime dependency.
"""
import datetime
import json
import os

from Logger.logger import logger
from Util.util import write_if_different

from ComplianceReport import components

SBOM_DIRNAME = "ComplianceReport"
SBOM_FILENAME = "bom.json"
SPEC_VERSION = "1.5"
SCHEMA_URL = "http://cyclonedx.org/schema/bom-1.5.schema.json"

#: bumped when this module's own output shape changes
HARPIA_TOOL_VERSION = "0.1.0"


class ComplianceReport:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.messages = messages          # accepted for signature parity; unused here
        self.dest = dest
        self.compliance = compliance
        self.outDir = os.path.join(dest, "generated", SBOM_DIRNAME)
        self.log = logger(outFile=None, moduleName="ComplianceReport")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        bom = self._build_bom()
        write_if_different(os.path.join(self.outDir, SBOM_FILENAME),
                           json.dumps(bom, indent=2) + "\n")
        self.log.print("emitted CycloneDX {} SBOM ({} components) into {}".format(
            SPEC_VERSION, len(bom["components"]), self.outDir))
        return None

    # -- assembly ----------------------------------------------------------

    def _build_bom(self):
        project = getattr(self.compliance, "project", None) or "default"
        return {
            "$schema": SCHEMA_URL,
            "bomFormat": "CycloneDX",
            "specVersion": SPEC_VERSION,
            "version": 1,
            "metadata": {
                "timestamp": _rfc3339_now(),
                "tools": [{
                    "vendor": "harpia",
                    "name": "harpia",
                    "version": HARPIA_TOOL_VERSION,
                }],
                "component": {
                    "type": "application",
                    "bom-ref": "harpia-project:{}".format(project),
                    "name": project,
                },
                "properties": self._harpia_properties(),
            },
            "components": self._components(),
        }

    def _harpia_properties(self):
        cc = self.compliance

        def enum_val(x):
            return x.value if hasattr(x, "value") else ("" if x is None else str(x))

        jurisdiction = ",".join(getattr(cc, "jurisdiction", []) or []) if cc else ""
        pairs = [
            ("harpia:risk_class", enum_val(getattr(cc, "risk_class", None))),
            ("harpia:topology", enum_val(getattr(cc, "topology", None))),
            ("harpia:phi_handling", enum_val(getattr(cc, "phi_handling", None))),
            ("harpia:crypto_backend", self._crypto_backend()),
            ("harpia:jurisdiction", jurisdiction),
        ]
        return [{"name": n, "value": v} for n, v in pairs]

    def _crypto_backend(self):
        path = os.path.join(self.dest, "build_metadata", "crypto_backend.json")
        try:
            with open(path, "r") as f:
                return json.load(f).get("crypto_backend") or components.UNKNOWN
        except (OSError, ValueError):
            return components.UNKNOWN

    def _components(self):
        out = []

        for name, sub, purl_type, description in components.VENDORED:
            version = components.vendored_version(sub)
            entry = {
                "type": "library",
                "bom-ref": "lib:{}".format(name),
                "name": name,
                "version": version,
                "description": description,
            }
            lic = components.vendored_license(sub)
            if lic:
                entry["licenses"] = [{"license": {"name": lic}}]
            src = components.vendored_source(sub)
            if src:
                entry["externalReferences"] = [{"type": "vcs", "url": src}]
            if version != components.UNKNOWN:
                entry["purl"] = "pkg:{}/{}@{}".format(purl_type, name, version)
            out.append(entry)

        for name, purl_type, description, cmds in components.ENVIRONMENT:
            version = components.environment_version(cmds)
            entry = {
                "type": "library",
                "bom-ref": "lib:{}".format(name),
                "name": name,
                "version": version,
                "description": description,
            }
            if version != components.UNKNOWN:
                entry["purl"] = "pkg:{}/{}@{}".format(purl_type, name, version)
            out.append(entry)

        return sorted(out, key=lambda c: c["name"])


def _rfc3339_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
