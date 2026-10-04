"""Copy a hand-written runtime module into the generated Python project.

The Python counterpart of the ``copy_if_different(<X>_RUNTIME_SRC, ...)``
pattern the C++ adapters use: a runtime is copied only by the adapter whose
feature needs it, under the dotted module name that adapter's ``*_common.py``
path constant gives, and every missing parent package gets an ``__init__.py``
so the module is importable (and documented by ``PyDocsAdapter``).
"""
import os

from Util.util import copy_if_different, write_if_different

_PACKAGE_DOCSTRING = '"""harpia runtime: ``{}``."""\n'


def copy_runtime_module(dest, src, dotted_module):
    """Copy ``src`` to ``<dest>/python/<dotted/module>.py``; write-if-different.

    Returns the destination path.
    """
    parts = dotted_module.split(".")
    py_root = os.path.join(dest, "python")
    for i in range(1, len(parts)):
        pkg_dir = os.path.join(py_root, *parts[:i])
        os.makedirs(pkg_dir, exist_ok=True)
        init = os.path.join(pkg_dir, "__init__.py")
        if not os.path.exists(init):
            write_if_different(init, _PACKAGE_DOCSTRING.format(".".join(parts[:i])))
    target = os.path.join(py_root, *parts[:-1], parts[-1] + ".py")
    copy_if_different(src, target)
    return target
