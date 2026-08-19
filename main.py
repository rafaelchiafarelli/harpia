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
from Database.SqlAdapter import SqlAdapter
from Database.CrudlAdapter import CrudlAdapter
from Database.MigrationAdapter import MigrationAdapter
from Database.DbIoAdapter import DbIoAdapter
from Database.RestAdapter import RestAdapter
from Database.SoapAdapter import SoapAdapter
from Database.WsdlAdapter import WsdlAdapter
from Database.GrpcServiceAdapter import GrpcServiceAdapter
from TestAdapter.TestAdapter import TestAdapter
from copy import deepcopy
from Util.util import (copyCMakeFiles, copyServerClientTemplates,
                       copyBasicProtos, chooseDemo, prune_stale_outputs)
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

    #0. pre-process check
    rootFile = pre_lex(folders=[localFolder], file=testFile, dest=testDestination, includeFolder = includeFolder)
    preProcessorResult = rootFile.process()

    if preProcessorResult is not None: ##no error detected
        log.print(preProcessorResult.__str__())
        exit(-1)
    listOfIncludes = rootFile.getListOfHarpias()
    log.print("{}".format(listOfIncludes))
    fileCounter = 0    
    lexicalAnalized = []
    mainFileLex = LexicalAnalyzer()
    mainFileAnalizedError = mainFileLex.process(testFile)
    if mainFileAnalizedError is not None:
        log.print("error in lexical analyzer for the main file")
        exit(-1)

    mainFileLex.CommentRemover()
    mainFileLex.ImportRemover()

    lastLex = mainFileLex
    for inc in listOfIncludes:
        incFilePreLex = pre_lex(folders=[localFolder], file=inc, dest=testDestination, includeFolder = includeFolder)
        incFilePreProcessorResult = incFilePreLex.process()
        if incFilePreProcessorResult is not None:
            log.print(incFilePreProcessorResult.__str__())
            exit(-1)
        analizer = LexicalAnalyzer()
        analizerError = analizer.process(inc)
        if analizerError is not None:
            log.print("error in lexical analyzer")
            exit(-1)
        analizer.CommentRemover()
        analizer.ImportRemover()
        lastLex = analizer

    lexicalAnalized += (lastLex.getTokens())

    msgFactory = MessageCreator(filename=testFile,tokens=lexicalAnalized, md5Hash=rootFile.getHash())

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
        fileCreator = FileCreator(message=msg,imports=imports , dest=testDestination)
        fileCreator.Process()
        fileCreator.save()
        #log.print(msgFactory.__str__())
    #copy what in the Assets folder to the build folder
    copyBasicProtos(src="./Assets/proto/protofiles", dest=testDestination)
    copyServerClientTemplates(src="./Assets", dest=testDestination, demo=chooseDemo(msgFactory.messages))
    copyCMakeFiles(src="./Assets", dest=testDestination)

    #7. compile the emitted .proto into C++ (requires protoc; provided by Docker)
    protoCompileError = ProtoCompiler(dest=testDestination).Process()
    if protoCompileError is not None:
        #non-fatal: protoc may be absent on the host, the earlier stages still ran
        log.print(protoCompileError.__str__())

    #9. generate the JSON adapters (header-only C++ over the protobuf messages)
    jsonAdapterError = JsonAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if jsonAdapterError is not None:
        log.print(jsonAdapterError.__str__())

    #13. generate the gRPC client/server stubs from the *_service.proto files
    grpcError = GrpcCompiler(dest=testDestination).Process()
    if grpcError is not None:
        #non-fatal: protoc / grpc_cpp_plugin may be absent on the host
        log.print(grpcError.__str__())

    #13 (zmq). generate the ZMQ/socket transport for push/pull + event/stream messages
    zmqError = ZmqAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if zmqError is not None:
        log.print(zmqError.__str__())

    #13 (grpc impl). wire the generated gRPC service to CRUDL (per table message)
    grpcSvcError = GrpcServiceAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if grpcSvcError is not None:
        log.print(grpcSvcError.__str__())

    #10. generate the XML adapters (reflection-based runtime + per-message wrappers)
    xmlError = XmlAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if xmlError is not None:
        log.print(xmlError.__str__())

    #8. pick the DB dialect (SQLite default; PostgreSQL via HARPIA_DB_BACKEND).
    # The generated DAO is dialect-free (SOCI); only the SQL the backend emits
    # (types, DDL, migration introspection, version stamp) changes.
    from Database.backends import get_backend
    dbBackend = get_backend(os.environ.get("HARPIA_DB_BACKEND"))
    log.print("DB backend: {} (soci:{})".format(
        dbBackend.name, dbBackend.soci_backend))

    #8. generate the SQL schema (supersedes the FileCreator stub)
    sqlError = SqlAdapter(messages=msgFactory.messages, dest=testDestination,
                          backend=dbBackend).Process()
    if sqlError is not None:
        log.print(sqlError.__str__())

    #8 (crudl). generate the CRUDL data-access objects (SOCI)
    crudlError = CrudlAdapter(messages=msgFactory.messages, dest=testDestination,
                              backend=dbBackend).Process()
    if crudlError is not None:
        log.print(crudlError.__str__())

    #8 (migrate). generate schema-migration / version-transform functions
    migrateError = MigrationAdapter(messages=msgFactory.messages,
                                    dest=testDestination,
                                    backend=dbBackend).Process()
    if migrateError is not None:
        log.print(migrateError.__str__())

    #8 (dbio). generate DB <-> JSON/XML bulk import/export (composes CRUDL + adapters)
    dbioError = DbIoAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if dbioError is not None:
        log.print(dbioError.__str__())

    #12. generate the REST bindings (HTTP CRUD over CRUDL + JSON)
    restError = RestAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if restError is not None:
        log.print(restError.__str__())

    #11. generate the SOAP endpoints (XML over HTTP, get/set over CRUDL)
    soapError = SoapAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if soapError is not None:
        log.print(soapError.__str__())

    #11 (WSDL). generate the WSDL descriptor for the SOAP service
    wsdlError = WsdlAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if wsdlError is not None:
        log.print(wsdlError.__str__())

    #14. generate the unit tests for the generated code (opt-in CTest target)
    testError = TestAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if testError is not None:
        log.print(testError.__str__())


    