##this is a file meant to be executed as the main executor
import os
from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from Logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex
from LexicalAnalizer.Remover import Remover
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
    rootFile = pre_lex(folders=[local_folder], file=testFile,dest="./build", includeFolder = includeFolder)
    preProcessorResult = rootFile.process()

    if preProcessorResult is None: ##no error detected
        listOfIncludes = rootFile.getListOfHarpias()
        log.print("{}".format(listOfIncludes))
        fileCounter = 0    
        lexicalAnalized = []
        mainFileLex = LexicalAnalyzer()
        mainFileAnalizedError = mainFileLex.process(testFile)
        if mainFileAnalizedError is not None:
            log.print("error in lexical analyzer for the main file")
            exit(-1)
        log.print("mainFileAnalized done")
        lexicalAnalized.append(deepcopy(mainFileLex))

        for inc in listOfIncludes:
            analizer = LexicalAnalyzer()
            analizerError = analizer.process(inc)
            if analizerError is not None:
                log.print("error in lexical analyzer")
                exit(-1)
            lexicalAnalized.append(deepcopy(analizer))
            log.print("appended the:{}".format(analizer.name))
            del analizer
        tokens = []
        remover = Remover()
        for lex in lexicalAnalized:
            log.print("process the:{}".format(lex.name))
            noCommentTokens = remover.CommentRemover(tokens=lex.getTokens())
            cleanTokens = remover.ImportRemover(tokens=noCommentTokens)
            tokens = tokens + deepcopy(cleanTokens)
        msgFactory = MessageCreator(filename=testFile,tokens=tokens, md5Hash=rootFile.getHash())
        for tok in tokens:
            
            messages = msgFactory.CreateMessages(beginToken=0)
            
            if messages != None:
                log.print(messages.__str__())
                exit(-1)
            
            for msg in msgFactory.messages:
                fileCreator = FileCreator(message=msg,imports=imports , dest="./build")
                fileCreator.Process()
                fileCreator.save()


            #log.print(msgFactory.__str__())
    else:
        log.print(preProcessorResult.__str__())
