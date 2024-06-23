
##this is a container file that will have all caracteristics for the messages
import copy
from message.Variables import Variables

class Message():
    access_modifiers = []
    name = ""
    variables = []
    table_name = ""
    visibility = ""
    def __init__(self, fileName, tok) -> None:
        self.tokens = copy.deepcopy(tok)
        self.file = fileName
    def Process(self):
        startOfVariables = 0
        endOfVariables = 0
        for j,token in enumerate(self.tokens):
            if token[0] == "MESSAGE":
                self.access_modifiers.append(self.tokens[0:j-1])
            if token[0] == "LBRACE":
                self.name = self.tokens[j-1][1]
                startOfVariables=j
            if token[0] == "RBRACE":
                endOfVariables = j
                v = Variables(filename=self.file,tok=self.tokens[startOfVariables:endOfVariables])
                ret = v.Process()
                if ret != None:
                    return ret
                self.variables = v.get()
            if j == len(self.tokens):
                if self.tokens[j][0] == "PCOMMA":
                    self.visibility = "PRIVATE"
                else:
                    self.visibility = "PUBLIC"
                if self.tokens[j-1][0] != "RBRACE":
                    self.table_name = self.tokens[j-1][1]

            


