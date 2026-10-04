"""The ``python`` backend: the Python target, generated *in addition to* C++.

Follows the rule lang-backend-seam fixed for ``java``: a second target is
additive on top of the full C++ pipeline, so :class:`PythonBackend` extends
:class:`~LangBackend.cpp.CppBackend`. The Python stages run first, after the
front end has emitted every ``.proto`` and copied the framework protos.
"""
from LangBackend.cpp import CppBackend


class PythonBackend(CppBackend):
    """C++ project + an installable Python project under ``<dest>/python/``."""

    name = "python"

    def run(self, ctx):
        self.run_python(ctx)
        super().run(ctx)

    def run_python(self, ctx):
        messages, dest, compliance = ctx.messages, ctx.dest, ctx.compliance

        # project layout + generation-time protoc (_pb2 / _pb2.pyi / _pb2_grpc)
        from PyAdapter.PyAdapter import PyAdapter
        ctx.report(PyAdapter(messages=messages, dest=dest,
                             compliance=compliance).Process())

        # (later epics add their stages here, above the docs)

        # Sphinx skeleton -- LAST: it documents every module already on disk
        from PyAdapter.PyDocsAdapter import PyDocsAdapter
        ctx.report(PyDocsAdapter(messages=messages, dest=dest,
                                 compliance=compliance).Process())
