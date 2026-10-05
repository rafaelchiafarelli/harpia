"""python-target / py-tests -- generated per-message unit tests (the Python
side of ``TestAdapter``'s per-message ``tests/<name>_<hash>_test.cpp``).

Emits ``<dest>/python/tests/test_<name>_<hash>.py`` per table-bearing message
(field access; JSON / XML / YAML round trips; the ``to_string`` façade -- a
round trip, or for a message whose tree carries ``phi`` the redaction
placeholder; a full CRUDL round trip on a temp-file
SQLite) plus ``tests/conftest.py``, and copies the reflective helpers as
``harpia_runtime.testing``. Run from ``<dest>/python``: ``pytest``.
"""
import os

from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_TEST = loadTemplate(__file__, "test_message.py.tmpl")
_RUNTIME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime", "testing.py")
TESTING_MODULE = "harpia_runtime.testing"

_CONFTEST = '''"""pytest configuration for the generated suite: import the project from
this checkout (``harpia_generated`` / ``harpia_runtime`` next to ``tests/``)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
'''



class PyTestAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "python", "tests")
        self.log = logger(outFile=None, moduleName="PyTestAdapter")

    def Process(self):
        tables = [m for m in self.messages
                  if not getattr(m, "isEnum", False) and m.tableName]
        if not tables:
            return None
        copy_runtime_module(self.dest, _RUNTIME, TESTING_MODULE)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "conftest.py"), _CONFTEST)
        for msg in tables:
            write_if_different(
                os.path.join(self.outDir, "test_{}_{}.py".format(msg.name, msg.md5Hash)),
                self._render(msg))
        self.log.print("generated {} Python test module(s) into {}".format(
            len(tables), self.outDir))
        return None

    def _render(self, msg):
        return _TEST.format(name=msg.name, hash=msg.md5Hash, table=msg.tableName)
