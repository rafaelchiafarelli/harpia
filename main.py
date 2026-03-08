##this is a file meant to be executed as the main executor
import os
from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from Logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex

from LexicalAnalizer.MessageCreator import MessageCreator,Message
from ProtoFile.ProtoFileProcessor import ProtoFileProcessor
from ProtoFile.FileCreator import FileCreator
from copy import deepcopy
from Util.util import copyCMakeFiles, copyServerClientTemplates, copyBasicProtos


def lexicalAnalizerProcessor(listOfIncludes, localFolder, testDestination, includeFolder):
    lexicalAnalizedInternaly = []
    for inc in listOfIncludes:
        
        incFilePreLex = pre_lex(folders=[localFolder], file=inc, dest=testDestination, includeFolder = includeFolder)
        incFilePreProcessorResult = incFilePreLex.process()
        listOfInsideIncludes = incFilePreLex.getListOfHarpias()
        
        if listOfInsideIncludes is not None and len(listOfInsideIncludes) > 0:
            lexicalAnalizedInternaly+=lexicalAnalizerProcessor(listOfInsideIncludes, localFolder, testDestination, includeFolder)
            
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
        log.print("lexical analizer for {} complete".format(analizer.getTokens()))
        lexicalAnalizedInternaly += analizer.getTokens()
        del analizer

    return lexicalAnalizedInternaly

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
    rootFileHash = rootFile.getHash()
    del rootFile
    log.print("{}".format(listOfIncludes))
    lexicalAnalized = []    
    #1. lexical analizer
    lexicalAnalized = lexicalAnalizerProcessor(listOfIncludes, localFolder, testDestination, includeFolder)
    
    #2. create messages
    log.print("amount of tokens: {}".format(lexicalAnalized.count(('ID', 'pope', 1, 8))))
    for t in lexicalAnalized:
        if t[0] == 'ID' and t[1] == 'pope':
            log.print("found pope token: {}".format(t))
    msgFactory = MessageCreator(filename=testFile,tokens=lexicalAnalized, md5Hash=rootFileHash)

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
    copyServerClientTemplates(src="./Assets", dest=testDestination)
    copyCMakeFiles(src="./Assets", dest=testDestination)

    
    