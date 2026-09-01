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
from Util.util import loadTemplate, write_if_different
from Util.gitstate import collect_git_state

from ComplianceReport import components, jurisdictions
from ComplianceReport.requirements import REQUIREMENTS

#: indirection so tests can monkeypatch the git read (same pattern as
#: ``_rfc3339_now``). The versioning epic emits its result as
#: ``harpia:git_*`` properties in ``bom.json``.
_collect_git_state = collect_git_state

SBOM_DIRNAME = "ComplianceReport"
SBOM_FILENAME = "bom.json"
TRACEABILITY_JSON = "traceability.json"
TRACEABILITY_MD = "traceability.md"
REPORT_PREFIX = "compliance_report"
SPEC_VERSION = "1.5"
SCHEMA_URL = "http://cyclonedx.org/schema/bom-1.5.schema.json"

_REPORT_TMPL = loadTemplate(__file__, "compliance_report.md.tmpl")

#: bumped when this module's own output shape changes
#: 0.2.0 -- versioning epic: six harpia:git_* properties added to bom.json
HARPIA_TOOL_VERSION = "0.2.0"


class ComplianceReport:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.messages = messages
        self.dest = dest
        self.compliance = compliance
        self.outDir = os.path.join(dest, "generated", SBOM_DIRNAME)
        self.log = logger(outFile=None, moduleName="ComplianceReport")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)

        bom = self._build_bom()
        write_if_different(os.path.join(self.outDir, SBOM_FILENAME),
                           json.dumps(bom, indent=2) + "\n")

        rows = self._traceability_rows()
        write_if_different(os.path.join(self.outDir, TRACEABILITY_JSON),
                           json.dumps({"rows": rows}, indent=2) + "\n")
        write_if_different(os.path.join(self.outDir, TRACEABILITY_MD),
                           _traceability_md(rows))

        reports = self._jurisdiction_reports(bom, rows)
        for fname, text in reports.items():
            write_if_different(os.path.join(self.outDir, fname), text)

        self.log.print(
            "emitted CycloneDX {} SBOM ({} components) + traceability matrix "
            "({} rows) + {} compliance report(s) into {}".format(
                SPEC_VERSION, len(bom["components"]), len(rows),
                len(reports), self.outDir))
        return None

    # -- jurisdiction-selected doc templates (task 3) -------------------

    def _jurisdiction_reports(self, bom, rows):
        """`{filename: markdown}`. Always a generic `compliance_report.md`;
        one `compliance_report.<token>.md` per entry in
        `compliance.jurisdiction` (same evidence, jurisdiction-specific
        header only). An unrecognized token falls back to the generic
        shell with a note."""
        out = {"{}.md".format(REPORT_PREFIX):
               self._render_report(jurisdictions.GENERIC, bom, rows)}

        for token in (getattr(self.compliance, "jurisdiction", None) or []):
            key, entry = jurisdictions.resolve(token)
            shell = entry or jurisdictions.GENERIC
            note = ("" if entry else
                    "> No jurisdiction-specific template for {!r}; the generic "
                    "baseline shell is used.".format(token))
            out["{}.{}.md".format(REPORT_PREFIX, key.lower())] = \
                self._render_report(shell, bom, rows, note)
        return out

    def _render_report(self, shell, bom, rows, note=""):
        def ctx(attr):
            v = getattr(self.compliance, attr, None)
            return v.value if hasattr(v, "value") else ("" if v is None else str(v))

        extra = "\n\n".join(p for p in (note.strip(),
                                        shell.get("extra_note", "").strip()) if p)
        subs = {
            "{{project}}": getattr(self.compliance, "project", None) or "default",
            "{{regime}}": shell["regime"],
            "{{doc_package}}": shell["doc_package"],
            "{{framework}}": shell["framework"],
            "{{standards}}": shell["standards"],
            "{{review_body}}": shell["review_body"],
            "{{postmarket}}": shell["postmarket"],
            "{{risk_class}}": ctx("risk_class"),
            "{{topology}}": ctx("topology"),
            "{{phi_handling}}": ctx("phi_handling"),
            "{{extra_note}}": extra,
            "{{sbom_table}}": _sbom_table(bom),
            "{{traceability_table}}": _traceability_table(rows),
        }
        text = _REPORT_TMPL
        for k, v in subs.items():
            text = text.replace(k, v)
        return text

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
        pairs.extend(self._git_properties())
        return [{"name": n, "value": v} for n, v in pairs]

    def _git_properties(self):
        """versioning epic: the git fork-lineage of the schema project being
        generated (read from the invoking working directory via
        `Util.gitstate`), as six `harpia:git_*` pairs appended after the
        `harpia:*` context pairs. Every value is a string -- `dirty`
        serializes as ``"true"`` / ``"false"``; an unavailable field is the
        string ``"unknown"`` (graceful-absence contract, never omitted).
        `run_pipeline.py::_collect_compliancereport` normalizes these to
        fixed sentinels so `test_golden.py` can snapshot `bom.json`."""
        st = _collect_git_state()

        def s(v):
            return "true" if v is True else "false" if v is False else str(v)

        return [
            ("harpia:git_commit", s(st["commit"])),
            ("harpia:git_ref", s(st["ref"])),
            ("harpia:git_dirty", s(st["dirty"])),
            ("harpia:git_describe", s(st["describe"])),
            ("harpia:git_origin_url", s(st["origin_url"])),
            ("harpia:git_parent_commit", s(st["parent_commit"])),
        ]

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

    # -- traceability matrix (task 2) -------------------------------------

    def _traceability_rows(self):
        """One row per (schema construct, applicable compliance requirement).
        Deterministic, no timestamp -- golden-snapshotted."""
        phi_reqs       = [r for r in REQUIREMENTS if r.applies_to == "phi_field"]
        phi_table_reqs = [r for r in REQUIREMENTS if r.applies_to == "phi_field_table"]
        crit_reqs      = [r for r in REQUIREMENTS if r.applies_to == "critical_message"]
        project_reqs   = [r for r in REQUIREMENTS if r.applies_to == "project"]

        rows = []

        def add(construct, req):
            rows.append({
                "construct": construct,
                "requirement_id": req.id,
                "rule_ref": req.rule_ref,
                "requirement": req.text,
                "mechanism": req.mechanism,
                "evidence": list(req.test_refs),
            })

        for msg in self.messages or []:
            if getattr(msg, "isEnum", False):
                continue
            has_table = bool(getattr(msg, "tableName", ""))
            if getattr(msg, "is_critical", False):
                for req in crit_reqs:
                    add(msg.name, req)
            for v in getattr(msg, "variables", None) or []:
                if not getattr(v, "is_phi", False):
                    continue
                construct = "{}.{}".format(msg.name, v.name)
                for req in phi_reqs:
                    add(construct, req)
                if has_table:
                    for req in phi_table_reqs:
                        add(construct, req)

        for req in project_reqs:
            add("(project)", req)

        rows.sort(key=lambda r: (r["construct"], r["requirement_id"]))
        return rows


def _traceability_table(rows):
    """The matrix as a bare Markdown table (header + separator + one row per
    entry). Shared by `traceability.md` and the jurisdiction reports."""
    lines = [
        "| Construct | Requirement | Rule | Mechanism | Evidence |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        evidence = "<br>".join("`{}`".format(e) for e in r["evidence"])
        req = "**{}** -- {}".format(r["requirement_id"],
                                    r["requirement"].replace("|", "\\|"))
        mech = r["mechanism"].replace("|", "\\|")
        lines.append("| `{}` | {} | {} | {} | {} |".format(
            r["construct"], req, r["rule_ref"], mech, evidence))
    return "\n".join(lines)


def _traceability_md(rows):
    return "\n".join([
        "# Traceability matrix",
        "",
        "One row per (schema construct, applicable compliance requirement): the",
        "requirement, the mechanism in the generated code that enforces it, and",
        "the test evidence. Generated by `ComplianceReport/` (process-artifacts",
        "epic). Source of truth is `traceability.json`.",
        "",
        _traceability_table(rows),
    ]) + "\n"


def _sbom_table(bom):
    lines = ["| Component | Version | License | PURL |",
             "|---|---|---|---|"]
    for c in bom.get("components", []):
        lic = ""
        for entry in c.get("licenses", []):
            lic = entry.get("license", {}).get("name", "") or lic
        lines.append("| {} | {} | {} | {} |".format(
            c.get("name", ""), c.get("version", ""), lic,
            "`{}`".format(c["purl"]) if c.get("purl") else ""))
    return "\n".join(lines)


def _rfc3339_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
