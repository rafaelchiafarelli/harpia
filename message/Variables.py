## this class will read all tokens and create a list of variables for them
import copy
from Errors.Error import Error, Types, Classes
from logger.logger import logger
import re
import uuid
class variable():
    index = -1
    name = ""
    regex = []
    type = None
    typeMap = []
    paginationSize = 0
    repeteableSize = 0
    modifiers = []
    constant = None
    def __str__(self) -> str:
        st = "index: {}, name:{}, type: {}, regex:{}, modifiers:{}".format(self.index,self.name, self.type,self.regex,self.modifiers)
        return st


class Variables():
    RegexForInt = "^[0-9]*$"
    RegexForFloat = "[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)"
    RegexForString = "\P{Cc}\P{Cn}\P{Cs}"
    md5Hash = None
    log = logger(outFile=None, moduleName="Variables" )
    variables = None
    file = None
    tokens = None
    isOneToMany = None
    dependencies = None
    def __init__(self,filename, tok,composedVariables,md5Hash,isOneToMany) -> None:
        self.tokens = copy.deepcopy(tok)
        self.file = filename
        self.md5Hash = md5Hash
        self.composedVariables = composedVariables
        self.variables = []
        self.dependencies = []
        ID = variable()
        ID.index = 0
        ID.name = 'ID_{}'.format(md5Hash)
        ID.type = ('INT','int','0','0')
        ID.regex = self.RegexForInt
        self.variables.append(ID)
        self.isOneToMany = isOneToMany

    def Process(self):
        curNewLine = 0
        curIndex = -1
        
        for j,token in enumerate(self.tokens):
            variableEnds = -1
            variableBegins = -1
            if token[0] == "NEWLINE":
                curNewLine = j
            if token[0] == 'PCOMMA':
                variableEnds = j+1
                variableBegins = curNewLine
                curNewLine = -1
                var = variable()
                regexEnd = 0
                regexStart = 0
                indexStart = 0
                firstID = 0
                
                for i,t in enumerate(self.tokens[variableBegins:variableEnds]):
                    if t[0] == 'REPETEABLE':
                        repeteable = self.getRepeteable(self.tokens[variableBegins+i:variableEnds])
                        if repeteable is None:
                            return Error(errCl=Classes.VARTYPES, 
                                        errTp=Types.MALFORMED_REPETEABLE, 
                                        FileName=self.file,
                                        FileLine=t[2],
                                        CharacterNumber=t[3])
                        
                        var.modifiers.append(pagination)
                    if t[0] == 'OPTIONAL':
                        firstID = i
                        var.modifiers.append(t)
                    if t[0] == 'UNIQUE':
                        firstID = i
                        var.modifiers.append(t)
                    if t[0] == 'REQUIRED':
                        firstID = i
                        var.modifiers.append(t)
                    if t[0] == 'PAGINATION':
                        firstID = i
                        pagination = self.getPagination(self.tokens[variableBegins+i:variableEnds])
                        if pagination is None:
                            return Error(errCl=Classes.VARTYPES, 
                                        errTp=Types.MALFORMED_PAGINATION, 
                                        FileName=self.file,
                                        FileLine=t[2],
                                        CharacterNumber=t[3])
                        
                        var.modifiers.append(t)
                        var.paginationSize = pagination

                    if t[0] == 'MAP':
                        firstID = -1
                        
                        mapTypes = self.getMap(self.tokens[variableBegins+i:variableEnds])
                        if mapTypes is None:
                            return Error(errCl=Classes.VARTYPES, 
                                        errTp=Types.MALFORMED_MAP, 
                                        FileName=self.file,
                                        FileLine=t[2],
                                        CharacterNumber=t[3])
                        
                        var.type = mapTypes[0]
                        var.typeMap = mapTypes

                    if firstID >= 0 and t[0] == 'ID':
                        firstID = -1
                        var.type = t  
                        regexStart = i

                    if t[0] == 'INT' or t[0] == 'FLOAT' or t[0] == 'STRING':
                        firstID = -1
                        var.type = t  
                        regexStart = i

                    if regexStart != 0 and t[0] == 'SQLEFTBRACKET':
                        regexStart = i
                    if regexStart != 0 and t[0] == 'SQRIGHTBRACKET':
                        regexEnd = i
                    if t[0] == 'ATTR':
                        indexStart = i
                    if indexStart != 0 and t[0] == 'INTEGER_CONST':
                        var.index = int(t[1])
                if var.index is None:
                    return Error(errCl=Classes.VARTYPES, 
                                 errTp=Types.VARIABLE_WITHOUT_INDEX, 
                                 FileName=self.file,
                                 FileLine=token[2],
                                 CharacterNumber=token[3])    
                if var.type is None:
                    return Error(errCl=Classes.VARTYPES, 
                                 errTp=Types.VARTYPE_NOT_DEFINED, 
                                 FileName=self.file,
                                 FileLine=token[2],
                                 CharacterNumber=token[3])
                if var.type[1] not in self.composedVariables:
                    if regexEnd > 0 and regexStart > 0:
                        var.regex = self.getRegex(self.tokens[regexStart+1:regexEnd+1])
                    else:
                        var.regex = self.getRegexFromType(var)
                    if var.type != 'INT' and var.type != 'FLOAT' and var.type != 'STRING' and var.regex is None:
                        self.log.print("error in var:{}".format(var.__str__()))
                        return Error(errCl=Classes.REGEX, 
                                errTp=Types.REGEX_NOT_FOUND, 
                                FileName=self.file,
                                FileLine=token[2],
                                CharacterNumber=token[3])
                else:
                    var.regex = var.type
                    if self.dependencies != None:
                        if var.type not in self.dependencies:
                            self.dependencies.append(var.type)


                if var.index > curIndex:
                    curIndex = var.index
                self.variables.append(var)
        if curIndex == -1:
            curIndex = 1
        self.AddHiddenVariables(lastIndex=curIndex)

        repeatedMsg = self.allUnique()
        if repeatedMsg is not None:
            self.log.print(repeatedMsg.__str__())
            return Error(errCl=Classes.VARTYPES, 
                errTp=Types.MULTIPLE_INSTANCES_OF_INDEX, 
                FileName=self.file,
                FileLine='0',
                CharacterNumber='0')
        return None
    
    def AddHiddenVariables(self, lastIndex):
        lastIndex+=1
        status = variable()
        status.index = lastIndex
        status.name = 'STATUS_{}'.format(str(self.md5Hash))
        status.type = ('STRING','string ','0','0')
        status.regex = self.RegexForString
        self.variables.append(status)
        lastIndex+=1
        error = variable()
        error.index = lastIndex
        error.name = "ERROR_{}".format(str(self.md5Hash))
        error.type = ('STRING','string ','0','0')
        error.regex = self.RegexForString
        self.variables.append(error)
        if self.isOneToMany is not None and self.isOneToMany == True:
            lastIndex+=1
            originator = variable()
            originator.index = lastIndex
            originator.name = "ORIGINATOR"
            originator.type = ('STRING','string','0','0')
            originator.regex = self.RegexForString
            originator.constant = {originator:str(self.md5Hash), uuid: str(uuid.uuid4())}
            self.variables.append(originator)
            
        


    def getRegexFromType(self, var):

        if var.type[0] == 'INT':
            return self.RegexForInt
        if var.type[0] == 'FLOAT':
            return self.RegexForFloat
        if var.type[0] == 'STRING':
            return self.RegexForString
        if var.type[0] == 'MAP':
            return self.RegexForMaps(var.typeMap)
        return None

    
    def RegexForMaps(self, varType):
        regexForType = []
        if len(varType) > 3 or len(varType) < 2:
            return None
        for t in varType:
            if t[0] == 'INT':
                regexForType.append(self.RegexForInt)
            if t[0] == 'FLOAT':
                regexForType.append(self.RegexForFloat)
            if t[0] == 'STRING':
                regexForType.append(self.RegexForString)
        
        return regexForType

    def getRegex(self, tokens ):
        if tokens[0][0] != 'SQLEFTBRACKET':
            return None
        repStart = 0
        repStop = 0
        for i,t in enumerate(tokens):
            if t[0] == 'SQLEFTBRACKET':
                repStart = i
            if t[0] == 'SQRIGHTBRACKET':
                repStop = i
        if repStop - repStart > 2:
            return None
        else:
            return tokens[repStart:repStop]        


    def getRepeteable(self,tokens):
        if tokens[0][0] != 'REPETEABLE':
            return None
        repStart = 0
        repStop = 0
        for i,t in enumerate(tokens):
            if t[0] == 'SQLEFTBRACKET':
                repStart = i
            if t[0] == 'SQRIGHTBRACKET':
                repStop = i
        regex = ""
        for t in tokens[repStart:repStop]:
            regex+=t[1]
        is_valid = False
        try:
            re.compile(regex)
            is_valid = True
        except re.error:
            return None
        if is_valid == True:
            return tokens[repStart:repStop]
        else:
            return None

    def getPagination(self, tokens):
        if tokens[0][0] != 'PAGINATION':
            return None
        pagStart = 0
        pagStop = 0
        pagination = None
        
        for i,t in enumerate(tokens):
            if t[0] == 'SQLEFTBRACKET':
                pagStart = i
            if t[0] == 'SQRIGHTBRACKET':
                pagStop = i
            if t[0] == 'INTEGER_CONST':
                pagination = int(t[1])
        if pagStop - pagStart > 2 or pagination is None:
            return None
        else:
            return pagination
        
    def getMap(self, tokens):
        
        if tokens[0][0] != 'MAP':
            return None
        mapStart = 0
        mapStop = 0
        maptypes = []
        for i,t in enumerate(tokens):
            if t[0] == 'INT':
                maptypes.append(t)
            if t[0] == 'FLOAT':
                maptypes.append(t)
            if t[0] == 'STRING':
                maptypes.append(t)
            if t[0] == 'LT':
                mapStart = i
            if t[0] == 'GT':
                mapStop = i
        if mapStop - mapStart < 2 or mapStop - mapStart > 4:
            return None
        else:
            return maptypes

    def allUnique(self):
        seen = set()
        if any(var.index in seen or seen.add(var.index) for var in self.variables) == True:
            return list(seen)[0]
        else:
            return None
        
    def get(self):
        return self.variables
    def __str__(self) -> str:
        st = ""
        if self.variables != None:
            for v in self.variables:
                st+= " {} \n".format(v.__str__())
        return st