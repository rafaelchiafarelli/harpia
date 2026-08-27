"""``ComplianceContext`` -- the project-wide compliance profile threaded
through every stage of the generator (Foundation F1).

Parsed once from ``project.harpia.yaml`` at generation start and passed into
every ``Stage*`` entry point, alongside the messages/dest args each already
takes. Per ``Initiatives/medical_devices/harpia_sensitive_data_design_rules.md``
§6a: ``risk_class`` is a single project-wide hardening floor (no
per-jurisdiction fan-out); ``jurisdiction[]`` is inert for codegen, read only
by Track M for paperwork-template selection.

F1 is plumbing only -- no stage branches on the values here yet. That starts
in later tracks (Track A/C/O/...).
"""
import os
from enum import Enum

import yaml

from Logger.logger import logger

_log = logger(outFile=None, moduleName="Compliance")

#: Default location of the project compliance config, relative to cwd (same
#: convention as ``main.py``'s HARPIA_INPUT_FILE/HARPIA_OUTPUT_DIR).
DEFAULT_CONFIG_PATH = "./project.harpia.yaml"

#: Env var override for the config path, mirroring HARPIA_INPUT_FILE etc.
CONFIG_PATH_ENV_VAR = "HARPIA_COMPLIANCE_CONFIG"

#: Fallback project name when ``project.harpia.yaml`` omits ``project``.
#: Used to key the environment-level public/private DB registry (Track K):
#: a PRIVATE table is reachable only by code declaring this same project
#: name, a PUBLIC one by anyone. A single-project build never has to set it.
DEFAULT_PROJECT = "default"


class RiskClass(Enum):
    """IEC 62304 software safety classification (see design-rules doc §6).
    ``CLASS_C`` is the strictest / fail-safe default."""
    CLASS_A = "class_a"
    CLASS_B = "class_b"
    CLASS_C = "class_c"


class Topology(Enum):
    """Deployment-exposure shape. Drives the F5 CryptoBackend/TLS seam
    alongside ``risk_class``. ``CLOUD_CONNECTED`` is the strictest / fail-safe
    default (most exposed)."""
    STANDALONE = "standalone"
    NETWORKED = "networked"
    CLOUD_CONNECTED = "cloud_connected"


class PhiHandling(Enum):
    """Project-level PHI policy, independent of any single field's ``phi``
    tag (design-rules doc §0). ``REQUIRED`` is the strictest / fail-safe
    default."""
    NONE = "none"
    OPT_IN = "opt_in"
    REQUIRED = "required"


class ComplianceConfigError(ValueError):
    """Raised when ``project.harpia.yaml`` exists but declares an unknown/
    invalid value for one of its fields -- a hard, fatal error at generation
    start, never silently ignored or defaulted (unlike an *absent* file or
    an absent field, which fall back to :func:`strictest_profile`)."""


class ComplianceContext:
    """The active compliance profile for one generation run.

    - ``risk_class``: project-wide hardening floor (§6a) -- mTLS/RBAC,
      tamper-evident audit storage, etc. once a later track consumes it.
      Never a per-jurisdiction build variant.
    - ``topology``: deployment-exposure shape, feeds the F5 CryptoBackend
      seam alongside ``risk_class``.
    - ``phi_handling``: whether/how this project declares PHI fields.
    - ``jurisdiction``: list of jurisdiction names. Inert for codegen --
      feeds Track M's paperwork-template selection only.
    - ``project``: this build's project name (Track K). Inert for every
      stage except the environment-level public/private DB registry, which
      stamps it as the owner of each table so a PRIVATE table can be
      refused to code from a different project. Defaults to
      :data:`DEFAULT_PROJECT`; a single-project build never sets it.
    """

    def __init__(self, risk_class, topology, phi_handling, jurisdiction=None,
                 project=None):
        self.risk_class = risk_class
        self.topology = topology
        self.phi_handling = phi_handling
        self.jurisdiction = list(jurisdiction) if jurisdiction else []
        self.project = project or DEFAULT_PROJECT

    def __repr__(self):
        return ("<ComplianceContext risk_class={} topology={} "
                "phi_handling={} jurisdiction={} project={}>").format(
            self.risk_class.value, self.topology.value,
            self.phi_handling.value, self.jurisdiction, self.project)


def strictest_profile():
    """The fail-safe default profile: highest risk_class, most exposed
    topology, mandatory phi_handling, no jurisdiction. Used when
    ``project.harpia.yaml`` is missing, or a field is present-but-unset --
    never for a field that's present with an unrecognized value (that's
    :class:`ComplianceConfigError` instead).

    ``project`` is not a hardening axis, so it just takes its default
    (:data:`DEFAULT_PROJECT`) here -- there is no "strictest" project name."""
    return ComplianceContext(risk_class=RiskClass.CLASS_C,
                              topology=Topology.CLOUD_CONNECTED,
                              phi_handling=PhiHandling.REQUIRED,
                              jurisdiction=[],
                              project=DEFAULT_PROJECT)


def _resolve_enum(enum_cls, raw, field_name, config_path):
    if raw is None:
        return None
    try:
        return enum_cls(raw)
    except ValueError:
        known = ", ".join(m.value for m in enum_cls)
        raise ComplianceConfigError(
            "invalid {} {!r} in {!r}; known values: {}".format(
                field_name, raw, config_path, known))


def load_compliance_context(path=None):
    """Parse ``project.harpia.yaml`` into a :class:`ComplianceContext`.

    - Missing file -> :func:`strictest_profile`, with a logged warning.
    - Existing file, a field omitted -> that field defaults to its
      strictest value, with a logged warning (rest of the file still
      applies normally).
    - Existing file, a field present but not one of its known values ->
      hard error (:class:`ComplianceConfigError`), never silently ignored.
    """
    config_path = path or os.environ.get(CONFIG_PATH_ENV_VAR, DEFAULT_CONFIG_PATH)

    if not os.path.isfile(config_path):
        strict = strictest_profile()
        _log.print(
            "no compliance config found at {!r}; defaulting to the "
            "strictest profile (risk_class={}, topology={}, "
            "phi_handling={})".format(config_path, strict.risk_class.value,
                                       strict.topology.value,
                                       strict.phi_handling.value))
        return strict

    with open(config_path, "r") as f:
        raw = yaml.safe_load(f) or {}

    if not isinstance(raw, dict):
        raise ComplianceConfigError(
            "{!r} must parse to a mapping, got {}".format(
                config_path, type(raw).__name__))

    strict = strictest_profile()

    risk_class = _resolve_enum(RiskClass, raw.get("risk_class"), "risk_class", config_path)
    if risk_class is None:
        _log.print("risk_class not set in {!r}; defaulting to the strictest "
                   "value ({})".format(config_path, strict.risk_class.value))
        risk_class = strict.risk_class

    topology = _resolve_enum(Topology, raw.get("topology"), "topology", config_path)
    if topology is None:
        _log.print("topology not set in {!r}; defaulting to the strictest "
                   "value ({})".format(config_path, strict.topology.value))
        topology = strict.topology

    phi_handling = _resolve_enum(PhiHandling, raw.get("phi_handling"), "phi_handling", config_path)
    if phi_handling is None:
        _log.print("phi_handling not set in {!r}; defaulting to the "
                   "strictest value ({})".format(config_path, strict.phi_handling.value))
        phi_handling = strict.phi_handling

    jurisdiction = raw.get("jurisdiction") or []
    if not isinstance(jurisdiction, list) or not all(isinstance(j, str) for j in jurisdiction):
        raise ComplianceConfigError(
            "jurisdiction in {!r} must be a list of strings, got {!r}".format(
                config_path, jurisdiction))

    project = raw.get("project")
    if project is None:
        _log.print("project not set in {!r}; defaulting to {!r}".format(
            config_path, DEFAULT_PROJECT))
        project = DEFAULT_PROJECT
    elif not isinstance(project, str) or not project.strip():
        raise ComplianceConfigError(
            "project in {!r} must be a non-empty string, got {!r}".format(
                config_path, project))

    return ComplianceContext(risk_class=risk_class, topology=topology,
                              phi_handling=phi_handling, jurisdiction=jurisdiction,
                              project=project)
