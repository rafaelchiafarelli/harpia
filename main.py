##this is a file meant to be executed as the main executor
import os
from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from Logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex

from LexicalAnalizer.MessageCreator import MessageCreator,Message
from ProtoFile.ProtoFileProcessor import ProtoFileProcessor
from ProtoFile.FileCreator import FileCreator
from copy import deepcopy
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

    local_folder = os.path.dirname(full_path)
    testFile = "./Test/test.harpia"
    includeFolder = "./Test/Include"
    #0. pre-process check
    rootFile = pre_lex(folders=[local_folder], file=testFile, dest="./build", includeFolder = includeFolder)
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
        incFilePreLex = pre_lex(folders=[local_folder], file=inc, dest="./build", includeFolder = includeFolder)
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

        fileCreator = FileCreator(message=msg,imports=imports , dest="./build")
        fileCreator.Process()
        fileCreator.save()


        #log.print(msgFactory.__str__())