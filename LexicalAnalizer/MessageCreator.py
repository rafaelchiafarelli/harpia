##this file will receive a clean (whitout comments) list of tokens and create separated messages

from message.Message import Message
from Errors.Error import Error, Types, Classes
import copy
from logger.logger import logger

class MessageCreator():
    log = logger(outFile=None,moduleName="MessageCreator")
    messages = []
    tokens = []
    def __init__(self,filename, tokens) -> None:
        self.file = filename
        ##must receive all the tokens and will devide in as many messages as needed
        self.tokens = copy.deepcopy(tokens)
    def CreateMessage(self):
        curNewLine = 0
        startMessage = -1
        endOfBody = -1
        endOfMessage = -1

        for i,token in enumerate(self.tokens):

            if token[0] == "NEWLINE":
                curNewLine = i
                if endOfBody != -1:
                    endOfMessage = curNewLine
            if token[0] == 'LBRACE':
                startMessage = curNewLine
            if token[0] == 'RBRACE':
                endOfBody = i
                if len(self.tokens) == i: ##it is the last one
                    endOfMessage = endOfBody
            if startMessage < endOfBody and startMessage < endOfMessage and endOfBody <= endOfMessage:
                self.log.print("starMessage:{} endOfBody:{} endOfMessage:{}".format(startMessage,endOfBody,endOfMessage))
                m = Message(fileName=self.file,tok=self.tokens[startMessage:endOfMessage])

                ret = m.Process()
                self.log.print("message:{}".format(m.__str__()))                
                if ret != None:
                    return ret
                
                self.messages.append(m)

                curNewLine = 0
                startMessage = -1
                endOfBody = -1
                endOfMessage = -1
        return None
    def get(self):
        return self.messages
    
    def __str__(self) -> str:
        return self.messages.__str__()