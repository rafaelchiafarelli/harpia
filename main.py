##this is a file meant to be executed as the main executor
import os
from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from Logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex
from LexicalAnalizer.Remover import Remover
from LexicalAnalizer.MessageCreator import MessageCreator,Message
from ProtoFile.ProtoFileProcessor import ProtoFileProcessor
from ProtoFile.FileCreator import FileCreator
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
    preProcessor = pre_lex(folders=[local_folder], file=testFile,dest="./build")
    preProcessorResult = preProcessor.process()

    if preProcessorResult is None: ##no error detected
        analizer = LexicalAnalyzer()

        with open(local_folder+testFile,"r") as inFile:
            while True:
                line = inFile.readline()
                if not line:
                    break
                analizer.tokenize(line)
            
            remover = Remover()
            noCommentTokens = remover.CommentRemover(tokens=analizer.getTokens())
            
            cleanTokens = remover.ImportRemover(tokens=noCommentTokens)
            imports = remover.files
            print(imports)
            msgFactory = MessageCreator(filename="test.harpia",tokens=cleanTokens, md5Hash=preProcessor.getHash())
            messages = msgFactory.CreateMessages(beginToken=0)
            
            if messages != None:
                log.print(messages.__str__())
                exit(-1)
            for msg in msgFactory.messages:
                fileCreator = FileCreator(message=msg,imports=imports , dest="./build")
                fileCreator.Process()
                fileCreator.save()
            #log.print(msgFactory.__str__())
