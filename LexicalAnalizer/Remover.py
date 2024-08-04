
## comment remover will remove all comments from the generated lexic
import copy
from logger.logger import logger
class Remover():
    tokens = []
    files = []
    def CommentRemover(self, tokens):
        original_tokens = []
        original_tokens = copy.deepcopy(tokens)
        for i,token in enumerate(original_tokens):
            if token[0] == 'COMMENT_LINE':
                for j,t in enumerate(original_tokens[i:]):
                    if t[0] == 'NEWLINE':
                        break
                del original_tokens[i:i+j-1]
            elif token[0] == 'COMMENT_START':
                for j,t in enumerate(original_tokens[i:]):
                    if t[0] == 'COMMENT_END':
                        break
                del original_tokens[i:i+j+1]
            else:
                self.tokens.append(token)
        return self.tokens
    

    def ImportRemover(self,tokens):
        original_tokens = []
        original_tokens = copy.deepcopy(tokens)
        currImport = None
        endPos = len(original_tokens)
        i = 0
        while i < endPos:

            if original_tokens[i][0] == 'IMPORT':
                currImport = i
            if original_tokens[i][0] == 'NEWLINE' and currImport is not None:
                fileName = self.parseImport(original_tokens[currImport:i])
                del original_tokens[currImport:i+1]
                endPos = len(original_tokens)
                i = i - (i+1-currImport)
                currImport = None
                self.files.append(fileName)
                
            i = i+1
        return original_tokens
    
    def parseImport(self, tokens):
        
        currQuotes = None
        ret = ""
        for i,token in enumerate(tokens):
            if token[0] == "QUOTES" and currQuotes is None:
                currQuotes = i
            if token[0] != "QUOTES" and currQuotes is not None:
                ret+=token[1]
        return ret