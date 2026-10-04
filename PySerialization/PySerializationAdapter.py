"""python-target / py-serialization -- the Python target's serialization
runtimes (JSON / XML / YAML / the redacting ``to_string`` façade).

Copies the hand-written modules under ``PySerialization/runtime/`` into the
generated project as ``harpia_runtime.<name>`` (``PyAdapter.runtime_copy``).
Every project has messages, so every runtime here is always copied, the
same as the C++ ``harpia_xml.h`` / ``harpia_yaml.h``.
"""
import os

from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("json.py", "harpia_runtime.json"),
    ("reflect.py", "harpia_runtime.reflect"),
    ("xml.py", "harpia_runtime.xml"),
    ("yaml.py", "harpia_runtime.yaml"),
)


class PySerializationAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.log = logger(outFile=None, moduleName="PySerializationAdapter")

    def Process(self):
        for src, module in RUNTIMES:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, src), module)
        self.log.print("copied {} serialization runtime(s)".format(len(RUNTIMES)))
        return None
