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
        
        

    def CreateMessages(self, beginToken, isInternal = False):
        curNewLine = 0
        startMessage = None
        endOfBody = None
        endOfMessage = None

        i = beginToken
        endPos = len(self.tokens)
        while i < endPos:

            if self.tokens[i][0] == "NEWLINE":
                curNewLine = i
                if endOfBody is not None:
                    endOfMessage = curNewLine

            if self.tokens[i][0] == 'LBRACE':
                startMessage = curNewLine

            if (self.tokens[i][0] == 'ENUM' or self.tokens[i][0] == 'MESSAGE') and startMessage is not None:

                endOfBody = None
                endOfMessage = None  
                i=i-1                 
                if self.CreateMessages(beginToken=curNewLine, isInternal=True) is not None:
                    return Error(errCl=Classes.MESSAGES, 
                            errTp=Types.MULTIPLE_INSTANCES_OF_MESSAGES, 
                            FileName=self.file,
                            FileLine=curNewLine,
                            CharacterNumber=curNewLine)
                

            if self.tokens[i][0] == 'RBRACE':
                endOfBody = i
                if len(self.tokens) == i: ##it is the last one
                    endOfMessage = endOfBody

            if startMessage is not None and endOfMessage is not None and endOfBody is not None:
                
                m = Message(fileName=self.file, 
                            availableMessages = self.availableMessages,
                            md5Hash = self.md5Hash)
                ret = m.Process(tokens=self.tokens[startMessage:endOfMessage])
                if ret != None:
                    self.log.print(ret.__str__())
                    return ret
                self.messages.append(m)
                self.availableMessages.append(m.name)
                del self.tokens[startMessage:endOfMessage]
                endPos = len(self.tokens)
                i = i - (endOfMessage-startMessage)
                curNewLine = 0
                startMessage = None
                endOfBody = None
                endOfMessage = None
                
                if isInternal is True:
                    return None
            i = i+1

        repeatedMsg = self.allUnique()
        if repeatedMsg is not None:
            self.log.print(repeatedMsg)
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

    def __str__(self) -> str:
        st = ""
        for msg in self.messages:
            st+=msg.__str__()+"\n"
        return st
