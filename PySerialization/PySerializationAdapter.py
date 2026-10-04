"""python-target / py-serialization -- the Python target's serialization
runtimes (JSON / XML / YAML / the redacting ``to_string`` façade).

Copies the hand-written modules under ``PySerialization/runtime/`` into the
generated project as ``harpia_runtime.<name>`` (``PyAdapter.runtime_copy``).
Every project has messages, so every runtime here is always copied, the
same as the C++ ``harpia_xml.h`` / ``harpia_yaml.h``.
"""
import os

from Compliance.audit_common import PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_PHI_TEMPLATE = loadTemplate(__file__, "phi_registry.py.tmpl")

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("json.py", "harpia_runtime.json"),
    ("reflect.py", "harpia_runtime.reflect"),
    ("xml.py", "harpia_runtime.xml"),
    ("yaml.py", "harpia_runtime.yaml"),
    ("redaction.py", "harpia_runtime.redaction"),
    ("redaction_audit.py", "harpia_runtime.redaction_audit"),
    ("serialize.py", "harpia_runtime.serialize"),
)

#: the generated phi registry (project-wide, from ``variable.is_phi``)
PHI_REGISTRY_MODULE = ("harpia_generated", "serialize", "phi_registry.py")


class PySerializationAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.log = logger(outFile=None, moduleName="PySerializationAdapter")

    def Process(self):
        for src, module in RUNTIMES:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, src), module)
        # redaction_audit records into the compliance AuditSink
        copy_runtime_module(self.dest, PY_AUDIT_SINK_RUNTIME_SRC, PY_AUDIT_SINK_MODULE)
        pairs = self._phi_pairs()
        pkg = os.path.join(self.dest, "python", *PHI_REGISTRY_MODULE[:-1])
        os.makedirs(pkg, exist_ok=True)
        write_if_different(os.path.join(pkg, "__init__.py"),
                           '"""Project-wide generated serialization tables."""\n')
        write_if_different(os.path.join(pkg, PHI_REGISTRY_MODULE[-1]),
                           self._render_phi_registry(pairs))
        self.log.print("copied {} serialization runtime(s); phi registry: {} field(s)".format(
            len(RUNTIMES), len(pairs)))
        return None

    def _phi_pairs(self):
        """(message, field) for every ``phi`` field, in schema order -- the
        same list ``SerializeAdapter`` renders for C++."""
        pairs = []
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                continue
            for v in getattr(msg, "variables", None) or []:
                if getattr(v, "is_phi", False):
                    pairs.append((msg.name, v.name))
        return pairs

    @staticmethod
    def _render_phi_registry(pairs):
        rows = "".join("\n    ({!r}, {!r}),".format(m, f) for m, f in pairs)
        rows = (rows + "\n") if rows else ""
        return _PHI_TEMPLATE.format(count=len(pairs), rows=rows)
