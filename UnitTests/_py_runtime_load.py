"""Load hand-written Python runtimes (``harpia_runtime.*``) for unit tests,
isolated from whatever generated tree another test module already imported
``harpia_runtime`` from (shared harness, not a test module).

``load_runtime(dest, [(module, src), ...], wanted)`` copies each runtime into
``<dest>/python/`` with ``copy_runtime_module`` (exactly as a generated
project gets it), imports ``wanted`` from there with every ``harpia_runtime``
entry of ``sys.modules`` set aside, then restores ``sys.modules`` and
``sys.path``. The returned modules keep working: their globals hold what they
imported.
"""
import importlib
import os
import sys

from PyAdapter.runtime_copy import copy_runtime_module


def load_runtime(dest, runtimes, wanted):
    for module, src in runtimes:
        copy_runtime_module(str(dest), src, module)
    root = os.path.join(str(dest), "python")

    def ours(name):
        return name == "harpia_runtime" or name.startswith("harpia_runtime.")

    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if ours(k)}
    sys.path.insert(0, root)
    try:
        return {name: importlib.import_module(name) for name in wanted}
    finally:
        sys.path.remove(root)
        for k in [k for k in sys.modules if ours(k)]:
            del sys.modules[k]
        sys.modules.update(saved)
