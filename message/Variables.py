## this class will read all tokens and create a list of variables for them
import copy
from Errors.Error import Error, Types, Classes
from logger.logger import logger


class variable():
    index = -1
    name = ""
    regex = []
    varDefinition = []
    modifiers = []
    def __str__(self) -> str:
        st = "index: {}, name:{}, varDefinition: [".format(self.index,self.name)
        for vD in self.varDefinition:
            st+="{}, ".format(vD.__str__())
        st+="], regex:{}, modifiers:{}".format(self.varDefinition,self.regex,self.modifiers)
        return st


class Variables():
    log = logger(outFile=None, moduleName="Variables" )
    variables = []
    file = None
    tokens =[]
    def __init__(self,filename, tok) -> None:
        self.tokens = copy.deepcopy(tok)
        self.file = filename
    def Process(self):
        curNewLine = 0

        for j,token in enumerate(self.tokens):
            variableEnds = -1
            variableBegins = -1
            if token[0] == "NEWLINE":
                curNewLine = j
            if token[0] == 'PCOMMA':
                variableEnds = j
                variableBegins = curNewLine
                curNewLine = -1
                var = variable()
                varTypeEnd = 0
                varTypeStart = 0
                varModfierStart = 0
                varModfierEnd = 0
                varNamePosition = 0
                regexEnd = 0
                regexStart = 0
                self.log.print(str(self.tokens[variableBegins:variableEnds]))
                for i,t in reversed(list(enumerate(self.tokens[variableBegins:variableEnds]))):
                    ##check for the variable consistency
                    self.log.print("t:{} i:{}".format(t[0],i))
                    if t[0] == 'INTEGER_CONST':
                        var.index = int(t[1])
                    if t[0] == 'ATTR':
                        varTypeEnd = i
                    if t[0] == 'SQLEFTBRACKET':
                        regexStart = i
                    if t[0] == 'SQRIGHTBRACKET':
                        regexEnd = i                        
                    if varNamePosition != 0:
                        if t[0] == 'MAP' or t[0] == 'INT' or t[0] == 'FLOAT' or t[0] == 'STRING' or t[0] == 'ID':
                            varTypeStart = i
                            self.log.print("varTypeStart:{}".format(varTypeStart))
                    if varTypeEnd != 0 and t[0] == 'ID':
                        var.name = t[1]
                        varNamePosition = i
                if regexEnd > 0 and regexStart > 0:
                    self.log.print("regexStart:{} regexEnd:{}".format(regexEnd,regexStart))
                    var.regex = self.tokens[regexStart+1:regexEnd+1]
                for i,t in enumerate(self.tokens[variableBegins:variableEnds]):
                    if varModfierStart == 0 and i < varTypeStart and t[0] == 'OPTIONAL' and t[0] == 'REPETEABLE' and t[0] == 'PAGINATION' and t[0] == 'REQUIRED':
                        varModfierStart = i
                    if varModfierStart > 0 and t[0] != 'OPTIONAL' and t[0] != 'REPETEABLE' and t[0] != 'PAGINATION' and t[0] != 'REQUIRED':
                        varModfierEnd = i

                if varModfierEnd > varTypeStart or varNamePosition > varTypeEnd:
                    return Error(errCl=Classes.MODIFIERS, 
                                 errTp=Types.MODIFIERS_BAD_POSITIONED, 
                                 FileName=self.file,
                                 FileLine=token[2],
                                 CharacterNumber=token[3])

                if varTypeStart == 0:
                    return Error(errCl=Classes.VARTYPES, 
                                 errTp=Types.VARTYPE_NOT_FOUND, 
                                 FileName=self.file,
                                 FileLine=token[2],
                                 CharacterNumber=token[3])
                var.varDefinition = self.tokens[varTypeStart+1:varNamePosition+1]
                self.log.print("varTypeStart:{} varNamePosition:{} varDefinition:{}".format(varTypeStart,varNamePosition,var.varDefinition))
                if varModfierEnd > 0 and varModfierEnd>varModfierStart:
                    var.modifiers = self.tokens[varModfierStart:varModfierEnd]
                self.variables.append(var)
                return None

    def get(self):
        return self.variables
    def __str__(self) -> str:
        st = ""
        if self.variables != None:
            for v in self.variables:
                st+= " {}".format(v.__str__())
        return st