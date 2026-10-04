"""The ``java`` backend: the Java target, generated *in addition to* C++.

``HARPIA_GEN_LANG=java`` has always meant "the full C++ project plus a
Gradle project under ``<dest>/java/``", so :class:`JavaBackend` extends
:class:`~LangBackend.cpp.CppBackend`: it runs the Java stages (``main.py``'s
former ``if genLang == "java":`` block, verbatim -- same adapters, order and
constructor arguments) and then the unchanged C++ pipeline. The Java stages
run first, as they did inline, after the front end has already copied the
framework protos (``GradleAdapter`` needs ``errorCode``/``heartBeat.proto``).
"""
from LangBackend.cpp import CppBackend


class JavaBackend(CppBackend):
    """C++ project + Gradle project under ``<dest>/java/``."""

    name = "java"

    def run(self, ctx):
        self.run_java(ctx)
        super().run(ctx)

    def run_java(self, ctx):
        messages, dest, compliance = ctx.messages, ctx.dest, ctx.compliance

        # Gradle project + gRPC stub wiring. Must run after the front end's
        # copyBasicProtos: it copies errorCode/heartBeat.proto from
        # <dest>/proto/protofiles/.
        from GradleAdapter.GradleAdapter import GradleAdapter
        ctx.report(GradleAdapter(messages=messages, dest=dest,
                                 compliance=compliance).Process())

        # 9 (java json). JSON pass-through -- a single hand-written runtime
        # class, not per-message generation (protobuf-java's Message/Builder
        # interfaces already make JsonFormat generic).
        from JavaJsonAdapter.JavaJsonAdapter import JavaJsonAdapter
        ctx.report(JavaJsonAdapter(messages=messages, dest=dest,
                                   compliance=compliance).Process())

        # 8 (java db). JDBC bind/extract runtime + generated CRUDL DAOs --
        # shares HARPIA_DB_BACKEND with the C++ target (ctx.db_backend, the
        # same object the C++ stages get).
        from JavaDatabase.JavaDbAdapter import JavaDbAdapter
        ctx.report(JavaDbAdapter(messages=messages, dest=dest,
                                 compliance=compliance).Process())

        from JavaDatabase.JavaCrudlAdapter import JavaCrudlAdapter
        ctx.report(JavaCrudlAdapter(messages=messages, dest=dest,
                                    backend=ctx.db_backend,
                                    compliance=compliance).Process())

        # 10 (java xml). reflection-based XML runtime -- one shared class, no
        # per-message generation, same reasoning as the JSON runtime above.
        from JavaXmlAdapter.JavaXmlAdapter import JavaXmlAdapter
        ctx.report(JavaXmlAdapter(messages=messages, dest=dest,
                                  compliance=compliance).Process())

        # 12 (java rest). REST CRUD over HttpServer -- reuses the JSON/XML
        # runtimes above for content negotiation and the DAOs.
        from JavaRestAdapter.JavaRestAdapter import JavaRestAdapter
        ctx.report(JavaRestAdapter(messages=messages, dest=dest,
                                   compliance=compliance).Process())

        # 11 (java soap). SOAP-over-HTTP envelope access -- hand-rolled, not a
        # real SOAP/WS-* stack, same as the C++ target.
        from JavaSoapAdapter.JavaSoapAdapter import JavaSoapAdapter
        ctx.report(JavaSoapAdapter(messages=messages, dest=dest,
                                   compliance=compliance).Process())

        # 13 (java zmq). ZMQ transport over JeroMQ. Reuses ZmqAdapter.py's own
        # origin-id derivation directly.
        from JavaZmqAdapter.JavaZmqAdapter import JavaZmqAdapter
        ctx.report(JavaZmqAdapter(messages=messages, dest=dest,
                                  compliance=compliance).Process())

        # 14 (java tests). Generated JUnit 5 tests -- field access, JSON/XML
        # round trip, DB CRUDL round trip.
        from JavaTestAdapter.JavaTestAdapter import JavaTestAdapter
        ctx.report(JavaTestAdapter(messages=messages, dest=dest,
                                   compliance=compliance).Process())
