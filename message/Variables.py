## this class will read all tokens and create a list of variables for them
import copy
from Errors.Error import Error, Types, Classes

class variable():
    index = -1
    name = ""
    varDefinition = []
    regex = []
    modifiers = []

class Variables():
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
                regexEnd = 0
                regexStart = 0
                for i,t in reversed(list(enumerate(self.tokens[variableBegins:variableEnds]))):
                    ##check for the variable consistency
                    if t[0] == 'INTEGER_CONST':
                        var.index = int(t[1])
                    if t[0] == 'ATTR':
                        varTypeEnd = i
                    if t[0] == 'SQLEFTBRACKET':
                        regexStart = i
                    if t[0] == 'SQRIGHTBRACKET':
                        regexEnd = i                        
                    if regexStart != 0 and varTypeEnd != 0 and t[0] == 'ID':
                        var.name = t[1]
                        varNamePosition = i
                    if var.name != "" and t[0] == 'MAP' or t[0] == 'INT' or t[0] == 'FLOAT' or t[0] == 'STRING' or t[0] == 'ID':
                        varTypeStart = i
                var.regex = self.tokens[regexStart:regexEnd]
                for i,t in enumerate(self.tokens[variableBegins:variableEnds]):
                    if t[0] == 'OPTIONAL' or t[0] == 'REPETEABLE' or t[0] == 'PAGINATION' or t[0] == 'REQUIRED':
                        varModfierStart = i
                    if varModfierStart != 0 and t[0] != 'OPTIONAL' and t[0] != 'REPETEABLE' and t[0] != 'PAGINATION' or t[0] != 'REQUIRED':
                        varModfierEnd = i

                if varModfierEnd < varTypeStart or varModfierEnd > varTypeStart or varNamePosition > varTypeEnd:
                    return Error(errCl=Classes.MODIFIERS, 
                                 errTp=Types.MODIFIERS_BAD_POSITIONED, 
                                 FileName=self.file,
                                 FileLine=token[2],
                                 CharacterNumber=token[3])
                var.varDefinition = self.tokens[varTypeStart:varNamePosition-1]
                var.modifiers = self.tokens[varModfierStart:varModfierEnd]
                self.variables.append(var)
                return None

    def get(self):
        return self.variables
