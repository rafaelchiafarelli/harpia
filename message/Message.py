
##this is a container file that will have all caracteristics for the messages
import copy
from message.Variables import Variables
from logger.logger import logger
class Message():
    log = logger(outFile=None, moduleName="Message")
    access_modifiers = []
    name = ""
    variables = []
    table_name = ""
    visibility = "PUBLIC"
    def __init__(self, fileName, tok) -> None:
        self.tokens = copy.deepcopy(tok)
        self.file = fileName

    def Process(self):
        startOfVariables = 0
        endOfVariables = 0
        namePosition = 0
        for j,token in enumerate(self.tokens):
            if namePosition == 0 and token[0] == 'ID':
                self.name = token[1]
                namePosition = j
                self.log.print("message name:{} at:{}".format(self.name,j))
            if token[0] == "MESSAGE":
                self.log.print("message received at:{}".format(j))
                self.access_modifiers = self.tokens[0:j-1]
            if token[0] == "LBRACE":
                startOfVariables=j
            if token[0] == "RBRACE":
                endOfVariables = j
                v = Variables(filename=self.file,tok=self.tokens[startOfVariables:endOfVariables])
                ret = v.Process()
                if ret != None:
                    return ret
                self.variables = v.get()
            if j >= len(self.tokens)-1:
                if self.tokens[j][0] == "PCOMMA":
                    self.visibility = "PRIVATE"
                else:
                    self.visibility = "PUBLIC"
                if self.tokens[j-1][0] != "RBRACE":
                    self.table_name = self.tokens[j-1][1]
            
        return None

    def __str__(self) -> str:
        st = "access_modifiers:{} name:{} variables:[".format(self.access_modifiers,self.name)
        for v in self.variables:

            st += "{}, ".format(v.__str__())
        st+="] table_name:{} visibility:{}".format(self.table_name,self.visibility)
        return st



