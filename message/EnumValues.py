## this class will read all tokens and create a list of variables for them
import copy
from Errors.Error import Error, Types, Classes
from logger.logger import logger
import re
import uuid


class EnumValues():
    md5Hash = None
    log = logger(outFile=None, moduleName="EnumValues" )
    values = []
    file = None
    tokens = None
    tmpValues = None
    tmpValue = None

    def __init__(self,filename, tok,composedVariables,md5Hash,isOneToMany) -> None:
        self.tokens = copy.deepcopy(tok)
        self.file = filename
        self.md5Hash = md5Hash
        self.composedVariables = composedVariables
        self.tmpValues = []
        


    def Process(self):
        curNewLine = 0
        tmpValues = []
        lastValid = 0
        
        #get the already defined values
        for j,token in enumerate(self.tokens):
            if token[0] == "NEWLINE":
                curNewLine = j
            if token[0] == 'PCOMMA':
                tmp = self.getValue(self.tokens[curNewLine:j+1])
                if tmp is not None:
                    return tmp
                if self.tmpValue[1] is not None:
                    tmpValues.append(self.tmpValue)
                    self.tmpValue = None

        repeatedMsg = self.allUnique()
        if repeatedMsg is not None:
            self.log.print(repeatedMsg.__str__())
            return Error(errCl=Classes.ENUMTYPES, 
                errTp=Types.MULTIPLE_INSTANCES_OF_INDEX, 
                FileName=self.file,
                FileLine=self.tokens[0][1],
                CharacterNumber=self.tokens[0][2])
        else:
            #store these values in
            if len(tmpValues) > 0:
                tmpValues.sort(key=lambda a: a[1])
                self.tmpValues = tmpValues
                lastValid = self.tmpValues[-1:][0][1]+1

        #get all that are not yet defined
        for j,token in enumerate(self.tokens):
            if token[0] == "NEWLINE":
                curNewLine = j
            if token[0] == 'PCOMMA':
                tmp = self.getValue(self.tokens[curNewLine:j+1])
                
                if tmp is None and self.tmpValue[1] is None:
                    self.tmpValue = (self.tmpValue[0],lastValid)
                    self.tmpValues.append(self.tmpValue)
                    lastValid = lastValid+1
                    self.tmpValue = None

        
        if self.tmpValues is not None and len(self.tmpValues) > 0:
            self.createValues()

        return None
    
    def createValues(self):
        for v in self.tmpValues:
            self.values.append(v)
            
    def getValue(self, tokens):

        if tokens[0][0] != "NEWLINE":
            return Error(errCl=Classes.ENUMTYPES, 
                errTp=Types.ENUM_VALUE_MUST_START_THE_LINE, 
                FileName=self.file,
                FileLine=tokens[0][2],
                CharacterNumber=tokens[0][3])
        if len(tokens[1:]) != 4 and len(tokens[1:]) != 2:
            
            return Error(errCl=Classes.ENUMTYPES, 
                errTp=Types.TOO_LONG_DEFINITION_OF_ENUMERATOR, 
                FileName=self.file,
                FileLine=tokens[0][2],
                CharacterNumber=tokens[0][3])
        
        if len(tokens[1:]) == 2:
            if tokens[1][0] == "ID" and tokens[2][0] == "PCOMMA":
                self.tmpValue = (tokens[1][1],None)
                return None
            else:
                return Error(errCl=Classes.ENUMTYPES, 
                    errTp=Types.NOT_VALID_ENUM, 
                    FileName=self.file,
                    FileLine=tokens[0][2],
                    CharacterNumber=tokens[0][3])

        if len(tokens[1:]) == 4:
            if tokens[1][0]  != "ID":
                return Error(errCl=Classes.ENUMTYPES, 
                    errTp=Types.ENUMNAME_NOT_VALID, 
                    FileName=self.file,
                    FileLine=tokens[0][2],
                    CharacterNumber=tokens[0][3])
            if tokens[2][0]  != "ATTR":
                return Error(errCl=Classes.ENUMTYPES, 
                    errTp=Types.EXPECTING_A_INTEGER_CONST_VALUE, 
                    FileName=self.file,
                    FileLine=tokens[0][2],
                    CharacterNumber=tokens[0][3])
            
            if  tokens[1][0]  == "ID" and tokens[2][0]  == "ATTR" and tokens[3][0]  == "INTEGER_CONST":
                self.tmpValue = (tokens[1][1],int(tokens[3][1]))
                return None
            else:
                
                return Error(errCl=Classes.ENUMTYPES, 
                    errTp=Types.MALFORMED_ENUM_TYPE, 
                    FileName=self.file,
                    FileLine=tokens[0][2],
                    CharacterNumber=tokens[0][3])                
        return Error(errCl=Classes.ENUMTYPES, 
                    errTp=Types.MALFORMED_ENUM_TYPE, 
                    FileName=self.file,
                    FileLine=tokens[0][2],
                    CharacterNumber=tokens[0][3])
                
            

    def allUnique(self):
        seen = set()
        if any(var.index in seen or seen.add(var.index) for var in self.tmpValues) == True:
            return list(seen)[0]
        else:
            return None
        
    def get(self):
        return self.tmpValues
    def __str__(self) -> str:
        st = ""
        if self.tmpValues != None:
            for v in self.tmpValues:
                st+= " {} \n".format(v.__str__())
        return st