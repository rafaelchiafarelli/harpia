
##this is a container file that will have all caracteristics for the messages
import copy
from message.Variables import Variables
from Errors.Error import Types, Classes, Error
from logger.logger import logger
class Message():
    log = None
    access_modifiers = None
    name = None
    variables = None
    availableMessages = None
    table_name = None
    visibility = None
    md5Hash = None
    def __init__(self, fileName, tok, availableMessages, md5Hash) -> None:
        self.tokens = copy.deepcopy(tok)
        self.file = fileName
        self.availableMessages = availableMessages
        self.variables = []
        self.access_modifiers = []
        self.log = logger(outFile=None, moduleName="Message")
        self.table_name = ""
        self.visibility = "PUBLIC"
        self.md5Hash = md5Hash


    def Process(self):
        startOfVariables = 0
        endOfVariables = 0
        msgReceived = False
        rBracePosition = None
        curNewLine = None
        isOneToMany = None
        for j,token in enumerate(self.tokens):
            if token[0] == 'NEWLINE':
                curNewLine = j

            if self.name is None and token[0] == 'ID':
                self.name = token[1]
    
            if msgReceived == False and token[0] == "MESSAGE" or  token[0] == "ENUM":
                if msgReceived == False:
                    msgReceived = True
                else:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.MESSAGES_INSIDE_MESSAGES_ARE_NOT_ALLOWED, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3])
                if curNewLine is None:
                    curNewLine = j
                self.access_modifiers = self.tokens[curNewLine+1:j]
                ##check if is a pull msg
                for access in self.access_modifiers:
                    if access[0] == 'PULL':
                        isOneToMany = True
                        break
            
            if token[0] == "LBRACE":
                startOfVariables=j
                if self.name is None:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3]) 
                
            if token[0] == "RBRACE":
                if startOfVariables is None:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3])  
                endOfVariables = j
                
                v = Variables(filename=self.file,
                              tok=self.tokens[startOfVariables:endOfVariables], 
                              composedVariables= self.availableMessages,
                              md5Hash=self.md5Hash,
                              isOneToMany=isOneToMany)
                ret = v.Process()
                if ret != None:
                    return ret
                self.variables = v.get()
                rBracePosition = j
            
            if rBracePosition is not None:
                if token[0] == "PCOMMA":
                    self.visibility = "PRIVATE"
                if token[0] == 'ID':
                    self.table_name = self.tokens[j-1][1]
        if self.name is None:
            return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine='1',
                        CharacterNumber='1')
        return None

    def __str__(self) -> str:
        st = "access_modifiers:{} name:{} variables:[".format(self.access_modifiers,self.name)
        for v in self.variables:

            st += "{}, ".format(v.__str__())
        st+="] table_name:{} visibility:{} \n".format(self.table_name,self.visibility)
        return st



