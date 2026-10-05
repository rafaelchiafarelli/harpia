##this is a file meant to be executed as the main executor
import os
from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from Logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex

from LexicalAnalizer.MessageCreator import MessageCreator,Message
from ProtoFile.ProtoFileProcessor import ProtoFileProcessor
from ProtoFile.FileCreator import FileCreator
from copy import deepcopy
from Util.util import copyBasicProtos, prune_stale_outputs
from Compliance.context import load_compliance_context, ComplianceConfigError
from Crypto.backend import get_backend as get_crypto_backend, write_build_metadata as write_crypto_build_metadata
from LangBackend import GenerationContext, get_lang_backend
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

    #-1 (language). pick the generation target (LangBackend registry; default
    # cpp). Resolved before any output is written so an unknown
    # HARPIA_GEN_LANG fails fast instead of silently generating C++ only.
    try:
        langBackend = get_lang_backend(os.environ.get("HARPIA_GEN_LANG"))
    except ValueError as e:
        log.print(str(e))
        exit(-1)
    log.print("Generation target: {}".format(langBackend.name))

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

    #copy the framework protos (errorCode/heartBeat/capabilities) every
    # language backend builds on -- before the backend runs.
    copyBasicProtos(src="./Assets/proto/protofiles", dest=testDestination)

    #8. pick the DB dialect (SQLite default; PostgreSQL via HARPIA_DB_BACKEND).
    # Resolved here, once, rather than inside a language backend: every
    # target's DB layer shares this exact selector -- same env var, same
    # backend object, threaded into each target's DAOs so none can silently
    # drift from another's dialect for a given run.
    from Database.backends import get_backend
    dbBackend = get_backend(os.environ.get("HARPIA_DB_BACKEND"))
    log.print("DB backend: {} (soci:{})".format(
        dbBackend.name, dbBackend.soci_backend))

    #6-15. everything after the front end belongs to the selected language
    # backend (LangBackend/): cpp by default, java = cpp + a Gradle project.
    # dbBackend / cryptoBackend ride on the context so every target in this
    # run shares the identical objects.
    langBackend.run(GenerationContext(messages=msgFactory.messages,
                                      dest=testDestination,
                                      compliance=complianceContext,
                                      db_backend=dbBackend,
                                      crypto_backend=cryptoBackend,
                                      root_hash=rootFile.getHash(),
                                      log=log))
