"""The ``cpp`` backend: harpia's native C++ pipeline, the default target.

This is ``main.py``'s former unconditional stage list, moved here verbatim
(same adapters, same order, same constructor arguments). Every stage is
non-fatal: an ``Error`` is logged and the next stage still runs.
"""
from LangBackend.base import LangBackend

from ProtoFile.ProtoCompiler import ProtoCompiler
from ProtoFile.GrpcCompiler import GrpcCompiler
from JsonAdapter.JsonAdapter import JsonAdapter
from ZmqAdapter.ZmqAdapter import ZmqAdapter
from DdsAdapter.DdsAdapter import DdsAdapter
from Callback.CallbackAdapter import CallbackAdapter
from XmlAdapter.XmlAdapter import XmlAdapter
from YamlAdapter.YamlAdapter import YamlAdapter
from SerializeAdapter.SerializeAdapter import SerializeAdapter
from ComplianceReport.ComplianceReport import ComplianceReport
from Database.SqlAdapter import SqlAdapter
from Database.CrudlAdapter import CrudlAdapter
from Database.DbRegistryAdapter import DbRegistryAdapter
from Database.MigrationAdapter import MigrationAdapter
from Database.DbIoAdapter import DbIoAdapter
from Database.RestAdapter import RestAdapter
from Database.SoapAdapter import SoapAdapter
from Database.WsdlAdapter import WsdlAdapter
from SdcAdapter.SdcAdapter import SdcAdapter
from Database.GrpcServiceAdapter import GrpcServiceAdapter
from GrpcCapabilityAdapter.GrpcCapabilityAdapter import GrpcCapabilityAdapter
from HttpCapabilityAdapter.HttpCapabilityAdapter import HttpCapabilityAdapter
from ZmqCapabilityAdapter.ZmqCapabilityAdapter import ZmqCapabilityAdapter
from TestAdapter.TestAdapter import TestAdapter
from Util.util import (copyCMakeFiles, copyServerClientTemplates,
                       copyDoxygenFiles, chooseDemo)
from Doxygen.mainpage import write_mainpage as write_doxygen_mainpage


class CppBackend(LangBackend):
    """Generate the C++ project (CMake, protobuf/gRPC, SOCI DAOs, transports)."""

    name = "cpp"

    def run(self, ctx):
        messages, dest, compliance = ctx.messages, ctx.dest, ctx.compliance

        # server/client demo sources + the CMake build tree
        copyServerClientTemplates(src="./Assets", dest=dest, demo=chooseDemo(messages))
        copyCMakeFiles(src="./Assets", dest=dest)

        #6 (doxygen). Doxyfile + assembled mainpage (Foundation F6) -- one-time
        # infrastructure; see Doxygen/mainpage.py for why the mainpage is
        # assembled fresh every run instead of a static copy.
        copyDoxygenFiles(src="./Assets", dest=dest)
        write_doxygen_mainpage(dest)

        #7. compile the emitted .proto into C++ (requires protoc; provided by
        # Docker). Non-fatal: protoc may be absent on the host.
        ctx.report(ProtoCompiler(dest=dest, compliance=compliance).Process())

        #9. JSON adapters (header-only C++ over the protobuf messages)
        ctx.report(JsonAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #13. gRPC client/server stubs from the *_service.proto files
        # (non-fatal: protoc / grpc_cpp_plugin may be absent on the host)
        ctx.report(GrpcCompiler(dest=dest, compliance=compliance).Process())

        #13 (zmq). ZMQ/socket transport for push/pull + event/stream messages
        ctx.report(ZmqAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #13 (events). in-process event/callback channels for
        # `event[cached/not-cached]` messages: one EventChannel<T> accessor per
        # event message + the hand-written runtime; the CRUDL DAO fires
        # publish() on create/update for the table-bearing ones.
        ctx.report(CallbackAdapter(messages=messages, dest=dest,
                                   compliance=compliance).Process())

        #13 (zmq capability handshake). advertise this project's message-type set
        ctx.report(ZmqCapabilityAdapter(messages=messages, dest=dest,
                                        rootHash=ctx.root_hash,
                                        compliance=compliance).Process())

        #13 (dds). DDS transport for messages carrying the `dds` modifier
        # (non-fatal: NOTHING_TO_REPORT when no message declares `dds`)
        ctx.report(DdsAdapter(messages=messages, dest=dest, compliance=compliance,
                              crypto_backend=ctx.crypto_backend).Process())

        #13 (grpc impl). wire the generated gRPC service to CRUDL (per table message)
        ctx.report(GrpcServiceAdapter(messages=messages, dest=dest, compliance=compliance,
                                      crypto_backend=ctx.crypto_backend).Process())

        #13 (grpc capability handshake). advertise this project's message-type set
        ctx.report(GrpcCapabilityAdapter(messages=messages, dest=dest,
                                         rootHash=ctx.root_hash,
                                         compliance=compliance).Process())

        #10. XML adapters (reflection-based runtime + per-message wrappers)
        ctx.report(XmlAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #10 (yaml). YAML adapters (reflection-based runtime + wrappers)
        ctx.report(YamlAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #10 (serialize). unified JSON/XML/YAML toString façade
        ctx.report(SerializeAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #8. SQL schema (supersedes the FileCreator stub)
        ctx.report(SqlAdapter(messages=messages, dest=dest,
                              backend=ctx.db_backend, compliance=compliance).Process())

        #8 (crudl). CRUDL data-access objects (SOCI)
        ctx.report(CrudlAdapter(messages=messages, dest=dest,
                                backend=ctx.db_backend, compliance=compliance).Process())

        #8 (registry). environment-level public/private DB registry +
        # cross-project access check; one project-wide header, additive.
        ctx.report(DbRegistryAdapter(messages=messages, dest=dest,
                                     compliance=compliance).Process())

        #8 (migrate). schema-migration / version-transform functions
        ctx.report(MigrationAdapter(messages=messages, dest=dest,
                                    backend=ctx.db_backend, compliance=compliance).Process())

        #8 (dbio). DB <-> JSON/XML bulk import/export (composes CRUDL + adapters)
        ctx.report(DbIoAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #12. REST bindings (HTTP CRUD over CRUDL + JSON)
        ctx.report(RestAdapter(messages=messages, dest=dest, compliance=compliance,
                               crypto_backend=ctx.crypto_backend).Process())

        #11. SOAP endpoints (XML over HTTP, get/set over CRUDL)
        ctx.report(SoapAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #11 (WSDL). WSDL descriptor for the SOAP service
        ctx.report(WsdlAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #11 (SDC). WS-Discovery responder that advertises the SOAP endpoint
        ctx.report(SdcAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #11/12 (http capability handshake). shared by REST and SOAP -- both
        # register routes on the same crow::SimpleApp in a real deployment.
        ctx.report(HttpCapabilityAdapter(messages=messages, dest=dest,
                                         rootHash=ctx.root_hash,
                                         compliance=compliance).Process())

        #14. unit tests for the generated code (opt-in CTest target)
        ctx.report(TestAdapter(messages=messages, dest=dest, compliance=compliance).Process())

        #15. compliance report -- CycloneDX SBOM for the generated project
        # python-target / py-artifacts: a python run (PythonBackend extends this
        # class) also lists the generated Python package's dependencies
        ctx.report(ComplianceReport(messages=messages, dest=dest, compliance=compliance,
                                    python_target=self.name == "python").Process())
