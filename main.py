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
from copy import deepcopy
from Util.util import copyCMakeFiles, copyServerClientTemplates, copyBasicProtos, chooseDemo
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
    testFile = "./HarpiaTest/test.harpia"
    includeFolder = "./HarpiaTest/Include"
    testDestination = "./HarpiaTest/test_build"
    
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
        
    lexicalAnalized += (analizer.getTokens())

    msgFactory = MessageCreator(filename=testFile,tokens=lexicalAnalized, md5Hash=rootFile.getHash())

    messagesErrors = msgFactory.CreateMessages(beginToken=0)
    if messagesErrors != None:
        log.print(messagesErrors.__str__())
        exit(-1)
    imports = []
    
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

    #10. generate the XML adapters (reflection-based runtime + per-message wrappers)
    xmlError = XmlAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if xmlError is not None:
        log.print(xmlError.__str__())

    #8. generate the SQL schema (supersedes the FileCreator stub)
    sqlError = SqlAdapter(messages=msgFactory.messages, dest=testDestination).Process()
    if sqlError is not None:
        log.print(sqlError.__str__())

    
    