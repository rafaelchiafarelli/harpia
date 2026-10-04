"""python-target / py-dds -- DDS transports (the Python side of
``DdsAdapter/DdsAdapter.py``).

Copies ``runtime/frame.py`` / ``runtime/transport.py`` as
``harpia_runtime.dds.frame`` / ``.transport`` and generates
``harpia_generated/dds/<name>_<hash>_dds.py`` for every message the C++
adapter emits a header for (the ``dds`` modifier; enums skipped).
"""
import os

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
        return _TEMPLATE.format(name=msg.name, hash=msg.md5Hash, topic=msg.name,
                                name_lit=repr(msg.name), qos_attrs=qos_attrs,
                                qos_doc=qos_doc)
