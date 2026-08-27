##this is a file meant to be executed as the main executor
import os
from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from Logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex

from LexicalAnalizer.MessageCreator import MessageCreator,Message
from ProtoFile.ProtoFileProcessor import ProtoFileProcessor
from ProtoFile.FileCreator import FileCreator
from ProtoFile.ProtoCompiler import ProtoCompiler
from ProtoFile.GrpcCompiler import GrpcCompiler
from JsonAdapter.JsonAdapter import JsonAdapter
from ZmqAdapter.ZmqAdapter import ZmqAdapter
from XmlAdapter.XmlAdapter import XmlAdapter
from YamlAdapter.YamlAdapter import YamlAdapter
from SerializeAdapter.SerializeAdapter import SerializeAdapter
from Database.SqlAdapter import SqlAdapter
from Database.CrudlAdapter import CrudlAdapter
from Database.DbRegistryAdapter import DbRegistryAdapter
from Database.MigrationAdapter import MigrationAdapter
from Database.DbIoAdapter import DbIoAdapter
from Database.RestAdapter import RestAdapter
from Database.SoapAdapter import SoapAdapter
from Database.WsdlAdapter import WsdlAdapter
from Database.GrpcServiceAdapter import GrpcServiceAdapter
from GrpcCapabilityAdapter.GrpcCapabilityAdapter import GrpcCapabilityAdapter
from HttpCapabilityAdapter.HttpCapabilityAdapter import HttpCapabilityAdapter
from ZmqCapabilityAdapter.ZmqCapabilityAdapter import ZmqCapabilityAdapter
from TestAdapter.TestAdapter import TestAdapter
from copy import deepcopy
from Util.util import (copyCMakeFiles, copyServerClientTemplates,
                       copyBasicProtos, copyDoxygenFiles, chooseDemo,
                       prune_stale_outputs)
from Compliance.context import load_compliance_context, ComplianceConfigError
from Crypto.backend import get_backend as get_crypto_backend, write_build_metadata as write_crypto_build_metadata
from Doxygen.mainpage import write_mainpage as write_doxygen_mainpage
if __name__ == '__main__':
    log = logger(outFile=None, moduleName="main" )
    log.print("Path at terminal when executing this file")
    log.print(os.getcwd() + "\n")
    log.print("This file path, relative to os.getcwd()")
    log.print(__file__ + "\n")

    log.print("This file full path (following symlinks)")
    full_path = os.path.realpath(__file__)
    log.print(full_path + "\n")

    log.print("This file directory and name")
    path, filename = os.path.split(full_path)
    log.print(path + ' --> ' + filename + "\n")

    log.print("This file directory only")
    log.print(os.path.dirname(full_path))

    localFolder = os.path.dirname(full_path)
    # Input/output are overridable via env so a wrapper (run_harpia.sh) can point
    # the generator at an arbitrary input folder / output folder. Defaults keep the
    # original in-repo behaviour.
    testFile = os.environ.get("HARPIA_INPUT_FILE", "./HarpiaTest/test.harpia")
    includeFolder = os.environ.get("HARPIA_INCLUDE_FOLDER", "./HarpiaTest/Include")
    testDestination = os.environ.get("HARPIA_OUTPUT_DIR", "./HarpiaTest/test_build")

    os.makedirs(testDestination, exist_ok=True)

    #-1. load the project-wide compliance profile (Foundation F1). An invalid/
    # unknown value in project.harpia.yaml is a hard error at generation
    # start; a missing file or an omitted field falls back to the strictest
    # profile instead (see Compliance/context.py).
    try:
        complianceContext = load_compliance_context()
    except ComplianceConfigError as e:
        log.print(str(e))
        exit(-1)

    #-1 (crypto). pick the crypto module a build would link against (Foundation
    # F5). Neither Track O (key-wrap/envelope-encryption) nor Track C (TLS
    # stack) exist in this repo yet, so nothing consumes this beyond the log
    # line + build-metadata sidecar below -- it's the seam, not the real thing.
    cryptoBackend = get_crypto_backend(os.environ.get("HARPIA_CRYPTO_BACKEND"),
                                       compliance=complianceContext)
    log.print("Crypto backend: {} (fips:{})".format(
        cryptoBackend.name, cryptoBackend.fips))
    write_crypto_build_metadata(cryptoBackend, testDestination)

    #0. pre-process check
    rootFile = pre_lex(folders=[localFolder], file=testFile, dest=testDestination, includeFolder = includeFolder, compliance=complianceContext)
    preProcessorResult = rootFile.process()

    if preProcessorResult is not None: ##no error detected
        log.print(preProcessorResult.__str__())
        exit(-1)
    listOfIncludes = rootFile.getListOfHarpias()
    log.print("{}".format(listOfIncludes))
    fileCounter = 0    
    lexicalAnalized = []
    mainFileLex = LexicalAnalyzer(compliance=complianceContext)
    mainFileAnalizedError = mainFileLex.process(testFile)
    if mainFileAnalizedError is not None:
        log.print("error in lexical analyzer for the main file")
        exit(-1)

    mainFileLex.CommentRemover()
    mainFileLex.ImportRemover()

    lastLex = mainFileLex
    for inc in listOfIncludes:
        incFilePreLex = pre_lex(folders=[localFolder], file=inc, dest=testDestination, includeFolder = includeFolder, compliance=complianceContext)
        incFilePreProcessorResult = incFilePreLex.process()
        if incFilePreProcessorResult is not None:
            log.print(incFilePreProcessorResult.__str__())
            exit(-1)
        analizer = LexicalAnalyzer(compliance=complianceContext)
        analizerError = analizer.process(inc)
        if analizerError is not None:
            log.print("error in lexical analyzer")
            exit(-1)
        analizer.CommentRemover()
        analizer.ImportRemover()
        lastLex = analizer

    lexicalAnalized += (lastLex.getTokens())

    msgFactory = MessageCreator(filename=testFile,tokens=lexicalAnalized, md5Hash=rootFile.getHash(), compliance=complianceContext)

    messagesErrors = msgFactory.CreateMessages(beginToken=0)
    if messagesErrors != None:
        log.print(messagesErrors.__str__())
        exit(-1)
    imports = []

    # Regeneration is write-if-different (every adapter below), so a stale
    # output -- a message renamed/removed since the last run, or a leftover
    # from a previous root-file hash -- is no longer cleaned up by a blanket
    # wipe. Remove exactly those before writing anything new.
    prune_stale_outputs(testDestination, rootFile.getHash(),
                        {m.name for m in msgFactory.messages})

    for msg in msgFactory.messages:
        fileCreator = FileCreator(message=msg,imports=imports , dest=testDestination, compliance=complianceContext)
        fileCreator.Process()
        fileCreator.save()
        #log.print(msgFactory.__str__())

    #copy what in the Assets folder to the build folder
    copyBasicProtos(src="./Assets/proto/protofiles", dest=testDestination)
    copyServerClientTemplates(src="./Assets", dest=testDestination, demo=chooseDemo(msgFactory.messages))
    copyCMakeFiles(src="./Assets", dest=testDestination)

    #8. pick the DB dialect (SQLite default; PostgreSQL via HARPIA_DB_BACKEND).
    # Resolved here (rather than down by the C++ Stage-8 calls below) because
    # the Java target's DB layer (J.5/J.8) shares this exact same selector --
    # same env var, same backend object, threaded into both targets' DAOs so
    # neither can silently drift from the other's dialect for a given run.
    from Database.backends import get_backend
    dbBackend = get_backend(os.environ.get("HARPIA_DB_BACKEND"))
    log.print("DB backend: {} (soci:{})".format(
        dbBackend.name, dbBackend.soci_backend))

    # 6/13 (java target selector). HARPIA_GEN_LANG picks the generation
    # target (default cpp, unchanged pipeline below); "java" additionally
    # stands up a Gradle project for the Java target (see Initiatives/multi-
    # language-targets/thread-1-java-target/README.md §5), including gRPC
    # stub wiring (J.3) -- run after copyBasicProtos so the framework protos
    # (errorCode/heartBeat) it needs already exist under
    # <dest>/proto/protofiles/. Not a per-dialect registry like
    # HARPIA_DB_BACKEND yet -- README §3 explicitly defers designing that
    # seam until a second language actually exists; this is the plain
    # env-var check that seam would eventually sit behind.
    genLang = os.environ.get("HARPIA_GEN_LANG", "cpp").strip().lower()
    if genLang == "java":
        from GradleAdapter.GradleAdapter import GradleAdapter
        gradleError = GradleAdapter(messages=msgFactory.messages,
                                    dest=testDestination,
                                    compliance=complianceContext).Process()
        if gradleError is not None:
            log.print(gradleError.__str__())

        # 9 (java json). JSON pass-through (J.4) -- a single hand-written
        # runtime class, not per-message generation (protobuf-java's
        # Message/Builder interfaces already make JsonFormat generic).
        from JavaJsonAdapter.JavaJsonAdapter import JavaJsonAdapter
        javaJsonError = JavaJsonAdapter(messages=msgFactory.messages,
                                        dest=testDestination,
                                        compliance=complianceContext).Process()
        if javaJsonError is not None:
            log.print(javaJsonError.__str__())

        # 8 (java db). JDBC bind/extract runtime (J.5) + generated CRUDL DAOs
        # (J.6) -- shares HARPIA_DB_BACKEND with the C++ target (dbBackend,
        # resolved above); J.8 (Postgres) is then just adding the
        # postgresql JDBC driver dependency, since this generation logic is
        # already dialect-neutral through the same DbBackend seam.
        from JavaDatabase.JavaDbAdapter import JavaDbAdapter
        javaDbError = JavaDbAdapter(messages=msgFactory.messages,
                                    dest=testDestination,
                                    compliance=complianceContext).Process()
        if javaDbError is not None:
            log.print(javaDbError.__str__())

        from JavaDatabase.JavaCrudlAdapter import JavaCrudlAdapter
        javaCrudlError = JavaCrudlAdapter(messages=msgFactory.messages,
                                          dest=testDestination,
                                          backend=dbBackend,
                                          compliance=complianceContext).Process()
        if javaCrudlError is not None:
            log.print(javaCrudlError.__str__())

        # 10 (java xml). reflection-based XML runtime (J.10 write path,
        # J.11 read path) -- one shared class, no per-message generation,
        # same reasoning as the JSON runtime above.
        from JavaXmlAdapter.JavaXmlAdapter import JavaXmlAdapter
        javaXmlError = JavaXmlAdapter(messages=msgFactory.messages,
                                      dest=testDestination,
                                      compliance=complianceContext).Process()
        if javaXmlError is not None:
            log.print(javaXmlError.__str__())

        # 12 (java rest). REST CRUD over HttpServer (J.12 routing/
        # credential-gate scaffolding, J.13 CRUDL handlers) -- reuses the
        # JSON/XML runtimes above for content negotiation and J.6's DAOs.
        from JavaRestAdapter.JavaRestAdapter import JavaRestAdapter
        javaRestError = JavaRestAdapter(messages=msgFactory.messages,
                                        dest=testDestination,
                                        compliance=complianceContext).Process()
        if javaRestError is not None:
            log.print(javaRestError.__str__())

        # 11 (java soap). SOAP-over-HTTP envelope access (J.15 parsing,
        # J.16 acceptance gate) -- hand-rolled, not a real SOAP/WS-* stack,
        # same as the C++ target; reuses the XML runtime and J.6's DAOs.
        from JavaSoapAdapter.JavaSoapAdapter import JavaSoapAdapter
        javaSoapError = JavaSoapAdapter(messages=msgFactory.messages,
                                        dest=testDestination,
                                        compliance=complianceContext).Process()
        if javaSoapError is not None:
            log.print(javaSoapError.__str__())

        # 13 (java zmq). ZMQ transport over JeroMQ (J.18 core, no CURVE --
        # J.19). Reuses ZmqAdapter.py's own origin-id derivation directly.
        from JavaZmqAdapter.JavaZmqAdapter import JavaZmqAdapter
        javaZmqError = JavaZmqAdapter(messages=msgFactory.messages,
                                      dest=testDestination,
                                      compliance=complianceContext).Process()
        if javaZmqError is not None:
            log.print(javaZmqError.__str__())

        # 14 (java tests). Generated JUnit 5 tests (J.21) -- field access,
        # JSON/XML round trip, DB CRUDL round trip, scoped to the same
        # columns JavaCrudlAdapter (J.6) handles.
        from JavaTestAdapter.JavaTestAdapter import JavaTestAdapter
        javaTestError = JavaTestAdapter(messages=msgFactory.messages,
                                        dest=testDestination,
                                        compliance=complianceContext).Process()
        if javaTestError is not None:
            log.print(javaTestError.__str__())

    #6 (doxygen). Doxyfile + assembled mainpage (Foundation F6) -- one-time
    # infrastructure; see Doxygen/mainpage.py for why the mainpage is
    # assembled fresh every run instead of a static copy.
    copyDoxygenFiles(src="./Assets", dest=testDestination)
    write_doxygen_mainpage(testDestination)

    #7. compile the emitted .proto into C++ (requires protoc; provided by Docker)
    protoCompileError = ProtoCompiler(dest=testDestination, compliance=complianceContext).Process()
    if protoCompileError is not None:
        #non-fatal: protoc may be absent on the host, the earlier stages still ran
        log.print(protoCompileError.__str__())

    #9. generate the JSON adapters (header-only C++ over the protobuf messages)
    jsonAdapterError = JsonAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if jsonAdapterError is not None:
        log.print(jsonAdapterError.__str__())

    #13. generate the gRPC client/server stubs from the *_service.proto files
    grpcError = GrpcCompiler(dest=testDestination, compliance=complianceContext).Process()
    if grpcError is not None:
        #non-fatal: protoc / grpc_cpp_plugin may be absent on the host
        log.print(grpcError.__str__())

    #13 (zmq). generate the ZMQ/socket transport for push/pull + event/stream messages
    zmqError = ZmqAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if zmqError is not None:
        log.print(zmqError.__str__())

    #13 (zmq capability handshake). advertise this project's message-type set
    zmqCapError = ZmqCapabilityAdapter(messages=msgFactory.messages,
                                       dest=testDestination,
                                       rootHash=rootFile.getHash(),
                                       compliance=complianceContext).Process()
    if zmqCapError is not None:
        log.print(zmqCapError.__str__())

    #13 (grpc impl). wire the generated gRPC service to CRUDL (per table message)
    grpcSvcError = GrpcServiceAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if grpcSvcError is not None:
        log.print(grpcSvcError.__str__())

    #13 (grpc capability handshake). advertise this project's message-type set
    grpcCapError = GrpcCapabilityAdapter(messages=msgFactory.messages,
                                         dest=testDestination,
                                         rootHash=rootFile.getHash(),
                                         compliance=complianceContext).Process()
    if grpcCapError is not None:
        log.print(grpcCapError.__str__())

    #10. generate the XML adapters (reflection-based runtime + per-message wrappers)
    xmlError = XmlAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if xmlError is not None:
        log.print(xmlError.__str__())

    #10 (yaml). generate the YAML adapters (reflection-based runtime + wrappers)
    yamlError = YamlAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if yamlError is not None:
        log.print(yamlError.__str__())

    #10 (serialize). unified JSON/XML/YAML toString façade (Track F / F.2)
    serializeError = SerializeAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if serializeError is not None:
        log.print(serializeError.__str__())

    #8. generate the SQL schema (supersedes the FileCreator stub)
    sqlError = SqlAdapter(messages=msgFactory.messages, dest=testDestination,
                          backend=dbBackend, compliance=complianceContext).Process()
    if sqlError is not None:
        log.print(sqlError.__str__())

    #8 (crudl). generate the CRUDL data-access objects (SOCI)
    crudlError = CrudlAdapter(messages=msgFactory.messages, dest=testDestination,
                              backend=dbBackend, compliance=complianceContext).Process()
    if crudlError is not None:
        log.print(crudlError.__str__())

    #8 (registry). environment-level public/private DB registry + cross-project
    # access check (Track K); one project-wide header, additive.
    registryError = DbRegistryAdapter(messages=msgFactory.messages,
                                      dest=testDestination,
                                      compliance=complianceContext).Process()
    if registryError is not None:
        log.print(registryError.__str__())

    #8 (migrate). generate schema-migration / version-transform functions
    migrateError = MigrationAdapter(messages=msgFactory.messages,
                                    dest=testDestination,
                                    backend=dbBackend, compliance=complianceContext).Process()
    if migrateError is not None:
        log.print(migrateError.__str__())

    #8 (dbio). generate DB <-> JSON/XML bulk import/export (composes CRUDL + adapters)
    dbioError = DbIoAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if dbioError is not None:
        log.print(dbioError.__str__())

    #12. generate the REST bindings (HTTP CRUD over CRUDL + JSON)
    restError = RestAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if restError is not None:
        log.print(restError.__str__())

    #11. generate the SOAP endpoints (XML over HTTP, get/set over CRUDL)
    soapError = SoapAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if soapError is not None:
        log.print(soapError.__str__())

    #11 (WSDL). generate the WSDL descriptor for the SOAP service
    wsdlError = WsdlAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if wsdlError is not None:
        log.print(wsdlError.__str__())

    #11/12 (http capability handshake). shared by REST and SOAP -- both
    # register routes on the same crow::SimpleApp in a real deployment.
    httpCapError = HttpCapabilityAdapter(messages=msgFactory.messages,
                                         dest=testDestination,
                                         rootHash=rootFile.getHash(),
                                         compliance=complianceContext).Process()
    if httpCapError is not None:
        log.print(httpCapError.__str__())

    #14. generate the unit tests for the generated code (opt-in CTest target)
    testError = TestAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()
    if testError is not None:
        log.print(testError.__str__())


    