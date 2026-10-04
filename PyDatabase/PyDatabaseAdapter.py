"""python-target / py-database -- the Python target's database layer.

Copies the hand-written DB runtime (``PyDatabase/runtime/`` →
``harpia_runtime.db.*``) into the generated project. The per-message DAOs
(task 2a onward) are generated here too, from the same ``Database/model.py``
analysis and the same ``DbBackend`` object the C++ and Java targets use.
"""
import os

from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("bind.py", "harpia_runtime.db.bind"),
)


class PyDatabaseAdapter:
    def __init__(self, messages, dest, backend=None, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.backend = backend
        self.log = logger(outFile=None, moduleName="PyDatabaseAdapter")

    def Process(self):
        for src, module in RUNTIMES:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, src), module)
        self.log.print("copied {} DB runtime module(s)".format(len(RUNTIMES)))
        return None
