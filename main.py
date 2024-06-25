##this is a file meant to be executed as the main executor

from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from logger.logger import logger
from LexicalAnalizer.pre_lex import pre_lex
from LexicalAnalizer.CommentRemover import CommentRemover
from LexicalAnalizer.MessageCreator import MessageCreator,Message
if __name__ == '__main__':
    log = logger(outFile=None, moduleName="main" )
    preProcessor = pre_lex(folders=["/home/rafael/workspace/harpia"], file="test.harpia")
    preProcessorResult = preProcessor.process()
    if preProcessorResult is None: ##no error detected
        analizer = LexicalAnalyzer()
        with open("/home/rafael/workspace/harpia/test.harpia","r") as inFile:
            while True:
                line = inFile.readline()
                if not line:
                    break
                analizer.tokenize(line)
            remover = CommentRemover()
            tokens = remover.remover(tokens=analizer.getTokens())
            msgFactory = MessageCreator(filename="test.harpia",tokens=tokens)
            messages = msgFactory.CreateMessage()
            if messages != None:
                log.print(messages.__str__())
                exit(-1)
            msgs = msgFactory.get()
            log.print(msgFactory.__str__())
