"""python-target / py-foundation task 3 -- the Sphinx skeleton for the
generated Python project (the Python counterpart of ``Doxygen/mainpage.py``,
Ground Rule 6).

Writes ``<dest>/python/docs/``: ``conf.py`` (autodoc + napoleon, Google-style
docstrings), ``index.rst`` and ``api.rst``. ``api.rst`` holds one
``automodule`` per harpia-written module found under ``harpia_runtime`` and
``harpia_generated`` (protoc output excluded), so it must run **last** among
the Python stages: every later epic's modules are already on disk and get
documented with no per-epic docs wiring.

The landing page links to ``USAGE_EXCERPT.md`` (written by the C++ pipeline,
which always runs alongside) instead of embedding it: Sphinx can't render
Markdown without ``myst-parser``, which the image doesn't carry.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different

_CONF_TEMPLATE = loadTemplate(__file__, "docs_conf.py.tmpl")
_INDEX_TEMPLATE = loadTemplate(__file__, "docs_index.rst.tmpl")
_API_TEMPLATE = loadTemplate(__file__, "docs_api.rst.tmpl")

_PACKAGES = ("harpia_runtime", "harpia_generated")
_PROTOC_SUFFIXES = ("_pb2.py", "_pb2_grpc.py")


def discover_modules(py_root):
    """Dotted names of every harpia-written module under the two packages,
    sorted; protoc output (``*_pb2*.py``) is skipped."""
    found = []
    for pkg in _PACKAGES:
        for root, dirs, files in os.walk(os.path.join(py_root, pkg)):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for fn in files:
                if not fn.endswith(".py") or fn.endswith(_PROTOC_SUFFIXES):
                    continue
                rel = os.path.relpath(os.path.join(root, fn), py_root)[:-3]
                parts = rel.split(os.sep)
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                found.append(".".join(parts))
    return sorted(found)


class PyDocsAdapter:
    def __init__(self, messages, dest, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.pyRoot = os.path.join(dest, "python")
        self.docsDir = os.path.join(self.pyRoot, "docs")
        self.log = logger(outFile=None, moduleName="PyDocsAdapter")

    def Process(self):
        os.makedirs(self.docsDir, exist_ok=True)
        modules = discover_modules(self.pyRoot)
        blocks = "\n".join(
            "{m}\n{u}\n\n.. automodule:: {m}\n   :members:\n".format(
                m=m, u="-" * len(m))
            for m in modules)
        write_if_different(os.path.join(self.docsDir, "conf.py"), _CONF_TEMPLATE)
        write_if_different(os.path.join(self.docsDir, "index.rst"), _INDEX_TEMPLATE)
        write_if_different(os.path.join(self.docsDir, "api.rst"),
                           _API_TEMPLATE.format(modules=blocks))
        self.log.print("Sphinx docs for {} module(s) under {}".format(
            len(modules), self.docsDir))
        return None
