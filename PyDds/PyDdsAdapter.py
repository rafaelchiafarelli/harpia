"""python-target / py-dds -- DDS transports (the Python side of
``DdsAdapter/DdsAdapter.py``).

Copies ``runtime/frame.py`` / ``runtime/transport.py`` as
``harpia_runtime.dds.frame`` / ``.transport`` and generates
``harpia_generated/dds/<name>_<hash>_dds.py`` for every message the C++
adapter emits a header for (the ``dds`` modifier; enums skipped).
"""
import os

from Compliance.audit_common import PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC
from Compliance.dds_common import DDS_SECURITY_DIR
from DdsAdapter.DdsAdapter import QUEUE_DEPTH, DdsAdapter
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_TEMPLATE = loadTemplate(__file__, "dds.py.tmpl")
_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")
#: (source file under runtime/, destination module)
RUNTIMES = (
    ("frame.py", "harpia_runtime.dds.frame"),
    ("transport.py", "harpia_runtime.dds.transport"),
    ("security.py", "harpia_runtime.dds.security"),
)
#: copied (with the audit sink) only when a `dds` message has a phi field
AUDIT_MODULE = "harpia_runtime.dds.audit"
DDS_EXT = "_dds.py"


class PyDdsAdapter:
    def __init__(self, messages, dest, compliance=None, crypto_backend=None) -> None:
        self.compliance = compliance
        self.crypto_backend = crypto_backend
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "harpia_generated", "dds")
        self.log = logger(outFile=None, moduleName="PyDdsAdapter")

    def _dds_messages(self):
        """Exactly the messages ``DdsAdapter`` emits a header for."""
        return [m for m in self.messages if not getattr(m, "isEnum", False)
                and "DDS" in DdsAdapter._modifiers(m)]

    def Process(self):
        msgs = self._dds_messages()
        if not msgs:
            return None
        for src, module in RUNTIMES:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, src), module)
        if any(DdsAdapter._phi_fields(m) for m in msgs):
            copy_runtime_module(self.dest, PY_AUDIT_SINK_RUNTIME_SRC, PY_AUDIT_SINK_MODULE)
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, "audit.py"),
                                AUDIT_MODULE)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "__init__.py"),
                           '"""Generated DDS transports, one module per `dds` message."""\n')
        for msg in msgs:
            write_if_different(
                os.path.join(self.outDir, "{}_{}{}".format(msg.name, msg.md5Hash, DDS_EXT)),
                self._render(msg))
        self._write_security(msgs)
        self.log.print("generated {} DDS transport(s) into {}".format(len(msgs), self.outDir))
        return None

    def _write_security(self, msgs):
        """py-dds task 3: the language-neutral DDS-Security documents
        (governance / permissions / selection) in
        ``harpia_generated/dds/security/``, written by ``DdsAdapter``'s own
        code (the python stages run before the C++ ones), so both targets
        carry the same bytes and the Python project is self-contained."""
        DdsAdapter(self.messages, self.dest, self.compliance,
                   crypto_backend=self.crypto_backend).write_security_documents(
            os.path.join(self.outDir, DDS_SECURITY_DIR), [m.name for m in msgs])

    def _render(self, msg):
        if getattr(msg, "is_critical", False):
            qos_attrs = "\n    CRITICAL = True\n    QUEUE_DEPTH = {}".format(QUEUE_DEPTH)
            qos_doc = ("``critical`` -- reliable, keep-all, at most {} samples "
                       "(design-rules §4a).".format(QUEUE_DEPTH))
        else:
            qos_attrs = ""
            qos_doc = "latest-value-only -- best-effort, keep-last(1) (design-rules §4b)."
        phi = DdsAdapter._phi_fields(msg)
        if phi:
            base = "AuditedPublisher"
            phi_attrs = "\n    PHI_FIELDS = {!r}".format(tuple(phi))
            doc = ("\n\n    ``{}`` carries phi: each ``publish()`` records one "
                   "``phi_publish`` event\n    (field names only) on ``audit_sink``.".format(
                       msg.name))
        else:
            base, phi_attrs, doc = "Publisher", "", ""
        publisher_import = ("from harpia_runtime.dds.audit import AuditedPublisher\n"
                            if phi else "")
        transport_import = "" if phi else "Publisher, "
        return _TEMPLATE.format(name=msg.name, hash=msg.md5Hash, topic=msg.name,
                                name_lit=repr(msg.name), qos_attrs=qos_attrs,
                                qos_doc=qos_doc, publisher_base=base,
                                publisher_import=publisher_import,
                                transport_import=transport_import,
                                phi_attrs=phi_attrs, publisher_doc=doc)
