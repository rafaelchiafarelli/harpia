##this is a file meant to be executed as the main executor
import os
from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex
from LexicalAnalizer.CommentRemover import CommentRemover
from LexicalAnalizer.MessageCreator import MessageCreator,Message
from protoFile.ProtoFileProcessor import ProtoFileProcessor
if __name__ == '__main__':
    print("Path at terminal when executing this file")
    print(os.getcwd() + "\n")
    print("This file path, relative to os.getcwd()")
    print(__file__ + "\n")

    print("This file full path (following symlinks)")
    full_path = os.path.realpath(__file__)
    print(full_path + "\n")

    print("This file directory and name")
    path, filename = os.path.split(full_path)
    print(path + ' --> ' + filename + "\n")

    print("This file directory only")
    print(os.path.dirname(full_path))
    local_folder = os.path.dirname(full_path)
    log = logger(outFile=None, moduleName="main" )
    preProcessor = pre_lex(folders=[local_folder], file="test.harpia")
    preProcessorResult = preProcessor.process()

    if preProcessorResult is None: ##no error detected
        analizer = LexicalAnalyzer()

        with open(local_folder+"/test.harpia","r") as inFile:
            while True:
                line = inFile.readline()
                if not line:
                    break
                analizer.tokenize(line)
            
            remover = CommentRemover()
            cleanTokens = remover.remover(tokens=analizer.getTokens())
            msgFactory = MessageCreator(filename="test.harpia",tokens=cleanTokens, md5Hash=preProcessor.getHash())
            messages = msgFactory.CreateMessages(beginToken=0)
            if messages != None:
                log.print(messages.__str__())
                exit(-1)
            #files = 
            log.print(msgFactory.__str__())
