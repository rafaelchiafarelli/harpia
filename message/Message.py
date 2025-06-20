
##this is a container file that will have all caracteristics for the messages
import copy
from Message.Variables import Variables
from Message.EnumValues import EnumValues
from Errors.Error import Types, Classes, Error
from Logger.logger import logger
class Message():
    log = None
    access_modifiers = None
    name = None
    variables = None
    availableMessages = None
    tableName = None
    visibility = None
    md5Hash = None
    dependency = None
    isEnum = False
    def __init__(self, fileName,availableMessages, md5Hash) -> None:

        self.file = fileName
        self.availableMessages = availableMessages
        self.variables = []
        self.access_modifiers = []
        self.log = logger(outFile=None, moduleName="Message")
        self.tableName = ""
        self.visibility = "PUBLIC"
        self.md5Hash = md5Hash


    def Process(self, tokens):
        startOfVariables = 0
        endOfVariables = 0
        msgReceived = False
        rBracePosition = None
        curNewLine = None
        isOneToMany = None
        isEnum = False
        lastToken = ""
        for j,token in enumerate(tokens):
            if token[0] == 'NEWLINE':
                curNewLine = j
    
            if token[0] == "MESSAGE" or  token[0] == "ENUM":
                if token[0] == "ENUM":
                    isEnum = True

                if curNewLine is None:
                    curNewLine = j
                if isEnum is False:
                    self.access_modifiers = tokens[curNewLine+1:j]
                    ##check if is a pull msg
                    for access in self.access_modifiers:
                        if access[0] == 'PULL' or access[0] == 'EVENT' or access[0] =='STREAM':
                            isOneToMany = True
                            break
            if lastToken == "MESSAGE" or  lastToken == "ENUM":
                if token[0] == "ID":
                    self.name = token[1]
                    
                else:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3]) 
            lastToken = token[0]

            if token[0] == "LBRACE":
                startOfVariables=j+1
                if self.name is None:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3]) 
                
            if token[0] == "RBRACE":
                if startOfVariables is None:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_MESSAGE_INITIALYSER, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3])  
  
                if isEnum == False:
                    endOfVariables = j-1
                    v = Variables(filename=self.file,
                                tok=tokens[startOfVariables:endOfVariables], 
                                composedVariables= self.availableMessages,
                                md5Hash=self.md5Hash,
                                isOneToMany=isOneToMany)
                    ret = v.Process()
                    if ret != None:
                        return ret
                    if v.dependencies != None:
                        self.dependency = v.dependencies
                    self.variables = v.get()
                    rBracePosition = j

                else:
                    endOfVariables = j-1
                    
                    v = EnumValues(filename=self.file,
                                tok=tokens[startOfVariables:endOfVariables], 
                                composedVariables= self.availableMessages,
                                md5Hash=self.md5Hash,
                                isOneToMany=isOneToMany)
                    ret = v.Process()
                    if ret != None:
                        return ret
                    self.variables = v.get()
                    rBracePosition = j

                self.isEnum = isEnum
            
            if rBracePosition is not None:
                if token[0] == "PCOMMA":
                    self.visibility = "PRIVATE"
                if token[0] == 'ID':
                    
                    self.tableName = tokens[j][1]

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
        st+="] tableName:{} visibility:{} \n".format(self.tableName,self.visibility)
        return st



