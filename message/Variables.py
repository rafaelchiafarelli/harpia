## this class will read all tokens and create a list of variables for them
import copy
import re
from Errors.Error import Error, Types, Classes
from logger.logger import logger
import uuid
class variable():
    index = -1
    name = ""
    regex = []
    type = None
    typeMap = []
    paginationSize = 0
    repeteableSize = 0
    modifiers = None
    constant = None
    renamedFrom = None
    def __init__(self) -> None:
        self.modifiers = []

    def __str__(self) -> str:
        st = "index: {}, name:{}, type: {}, regex:{}, modifiers:{} pag_size:{} renamed:{}".format(self.index,self.name, self.type,self.regex,self.modifiers,self.paginationSize,self.renamedFrom)
        return st


class Variables():
    RegexForInt = "^[0-9]*$"
    RegexForFloat = "[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)"
    RegexForString = r'(\\d+)\\n'
    md5Hash = None
    log = logger(outFile=None, moduleName="Variables" )
    variables = None
    file = None
    tokens = None
    isOneToMany = None
    dependencies = None
    def __init__(self,filename, tok,composedVariables,md5Hash,isOneToMany, compliance=None) -> None:
        self.compliance = compliance
        self.tokens = copy.deepcopy(tok)
        self.file = filename
        self.md5Hash = md5Hash
        self.composedVariables = composedVariables
        self.variables = []
        self.dependencies = []
        ID = variable()
        ID.index = 1
        ID.name = 'ID_{}'.format(md5Hash)
        ID.type = ('INT32','int','0','0')
        ID.regex = self.RegexForInt
        self.variables.append(ID)
        self.isOneToMany = isOneToMany

    def Process(self):
        curNewLine = 0
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
                firstID = 0
                currVarName = []
                for i,t in enumerate(self.tokens[variableBegins:variableEnds]):

                    if t[0] == 'REPETEABLE':
                        firstID = i
                        repeteable = self.getRepeteable(self.tokens[variableBegins+i:variableEnds])
                        if repeteable is None:
                            return Error(errCl=Classes.VARTYPES,
                                        errTp=Types.MALFORMED_REPETEABLE,
                                        FileName=self.file,
                                        FileLine=t[2],
                                        CharacterNumber=t[3])
                        # append the REPETEABLE token (like the other modifiers) so
                        # {m[0] for m in modifiers} can detect it; keep the bound
                        # separately as a memory hint.
                        var.modifiers.append(t)
                        var.repeteableSize = repeteable
                    if t[0] == 'OPTIONAL':
                        firstID = i
                        var.modifiers.append(t)
                    if t[0] == 'UNIQUE':
                        firstID = i
                        var.modifiers.append(t)
                    if t[0] == 'REQUIRED':
                        firstID = i
                        var.modifiers.append(t)
                    if t[0] == 'RENAMED_FROM':
                        firstID = i
                        var.modifiers.append(t)
                        var.renamedFrom = re.match(
                            r'renamed_from\[\s*([a-zA-Z]\w*)\s*\]', t[1]).group(1)
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

                    if t[0] == 'INT32' or t[0] == 'INT64' or t[0] == 'FLOAT' or t[0] == 'STRING':
                        firstID = -1
                        var.type = t  
                        regexStart = i

                    if regexStart != 0 and t[0] == 'SQLEFTBRACKET':
                        regexStart = i
                    if regexStart != 0 and t[0] == 'SQRIGHTBRACKET':
                        regexEnd = i

                    if t[0] == 'PCOMMA':
                        var.name = currVarName[1]
                        var.index = len(self.variables)+1
                        
                    currVarName = t
                    
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
                    if var.type != 'INT' and var.type != 'INT64' and var.type != 'FLOAT' and var.type != 'STRING' and var.regex is None:
                        
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
                self.variables.append(var)
                del var

        self.AddHiddenVariables(lastIndex=len(self.variables))

        repeatedMsg = self.allUnique()
        if repeatedMsg is not None:

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

        lastIndex+=1
        originator = variable()
        originator.index = lastIndex
        if self.isOneToMany is not None and self.isOneToMany == True:            
            originator.name = "ORIGINATOR_{}".format(self.md5Hash)
        else:
            originator.name = "ORIGINATOR"
        originator.type = ('STRING','string','0','0')
        originator.regex = self.RegexForString
        originator.constant = {originator:str(self.md5Hash), uuid: str(uuid.uuid4())}
        self.variables.append(originator)
            
        


    def getRegexFromType(self, var):
        self.log.print("getRegexFromType:{}".format(var.type))
        if var.type[0] == 'INT32':
            return self.RegexForInt
        if var.type[0] == 'INT64':
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
            if t[0] == 'INT32':
                regexForType.append(self.RegexForInt)
            if t[0] == 'INT64':
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
        # A repeateable is either unbounded ("repeteable", dynamic memory bound ->
        # size 0) or bounded to a constant ("repeteable[N]" -> N). The bound is the
        # first bracket pair right after the REPETEABLE token; a later regex bracket
        # on the field's type is not part of it. Returns the bound (int) or None on
        # a malformed/unbalanced bracket.
        if tokens[0][0] != 'REPETEABLE':
            return None
        repStart = next(
            (i for i, t in enumerate(tokens) if t[0] == 'SQLEFTBRACKET'), None)
        if repStart is None:
            return 0  # unbounded (dynamic)
        bound = None
        repStop = None
        for j in range(repStart + 1, len(tokens)):
            if tokens[j][0] == 'SQRIGHTBRACKET':
                repStop = j
                break
            if tokens[j][0] == 'INTEGER_CONST':
                bound = int(tokens[j][1])
        if repStop is None or bound is None:
            return None
        return bound

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
            if t[0] == 'INT32':
                maptypes.append(t)
            if t[0] == 'INT64':
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