##this file will receive a clean (whitout comments) list of tokens and create separated messages

from message.Message import Message
from Errors.Error import Error, Types, Classes
import copy
from logger.logger import logger

class MessageCreator():
    log = logger(outFile=None,moduleName="MessageCreator")
    messages = None
    tokens = None
    availableMessages = None
    def __init__(self,filename, tokens, md5Hash) -> None:
        self.md5Hash = md5Hash
        self.file = filename
        ##must receive all the tokens and will devide in as many messages as needed
        self.tokens = copy.deepcopy(tokens)
        self.messages = []
        self.availableMessages = []
        

    def CreateMessage(self):
        curNewLine = 0
        startMessage = None
        endOfBody = None
        endOfMessage = None

        for i,token in enumerate(self.tokens):

            if token[0] == "NEWLINE":
                curNewLine = i
                if endOfBody is not None:
                    endOfMessage = curNewLine

            if token[0] == 'LBRACE':
                startMessage = curNewLine
                
            if token[0] == 'RBRACE':
                endOfBody = i
                if len(self.tokens) == i: ##it is the last one
                    endOfMessage = endOfBody
            
            if startMessage is not None and endOfMessage is not None and endOfBody is not None:
  
                m = Message(fileName=self.file,
                            tok=self.tokens[startMessage:endOfMessage], 
                            availableMessages = self.availableMessages,
                            md5Hash = self.md5Hash)
                ret = m.Process()              
                if ret != None:
                    return ret
                
                self.messages.append(m)
                self.log.print("adding name:{}".format(m.name))
                self.availableMessages.append(m.name)
                self.log.print("available:{}".format(self.availableMessages.__str__()))
                curNewLine = 0
                startMessage = None
                endOfBody = None
                endOfMessage = None

        repeatedMsg = self.allUnique()
        if repeatedMsg is not None:
            return Error(errCl=Classes.MESSAGES, 
                errTp=Types.MULTIPLE_INSTANCES_OF_MESSAGES, 
                FileName=self.file,
                FileLine=repeatedMsg[2],
                CharacterNumber=repeatedMsg[3])
        
        return None
    
    def allUnique(self):
        seen = set()
        if any(msg.name in seen or seen.add(msg.name) for msg in self.messages) == True:
            return list(seen)[0]
        else:
            return None

    def generateMessages(self, prefix, sulfix):
        for msg in self.messages:
            pass
            with open("file",'w') as tmpProto:
                
                tmpProto.write()

    def __str__(self) -> str:
        st = ""
        for msg in self.messages:
            st+=msg.__str__()+"\n"
        return st
    def genMessage(self, message):
        for item in message:
            pass