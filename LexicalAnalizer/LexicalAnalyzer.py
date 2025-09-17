import re
from Logger.logger import logger
from Errors.Error import Error, Types, Classes

## LexicalAnalyzer should only tokenize the files 
class LexicalAnalyzer:
    log = logger(outFile=None, moduleName="LexicalAnalizer" )    
    # Token row
    lin_num = 1
    tokens = []
    def __init__(self) -> None:
        self.name = "empty"
        self.rules = [
            ('IMPORT', r'import'),
            ('QUOTES', r'\"'),
            ('POINT',r'\.'),
            ('ENUM', r'enum '),
            ('STREAM',r'stream '),
            ('PULL',r'pull '),
            ('PUSH',r'push '),
            ('EVENT',r'event '),
            ('PUSHPULL',r'pushpull '),
            ('MESSAGE',r'message '),
            ("OPTIONAL", r'optional '),
            ('REPETEABLE',r'repeteable'),
            ('PAGINATION',r'pagination'),
            ('REQUIRED',r'required '),
            ('UNIQUE',r'unique '),
            ('MAP', r'map'),            
            ('INT32', r'int'),            # int32
            ('INT64', r'int64'),            # int64
            ('FLOAT', r'float'),        # float
            ('STRING', r'string'),        # string
            ('LBRACKET', r'\('),        # (
            ('RBRACKET', r'\)'),        # )
            ('LBRACE', r'\{'),          # {
            ('RBRACE', r'\}'),          # }
            ('SQLEFTBRACKET', r'\['),          # [
            ('SQRIGHTBRACKET', r'\]'),          # ]
            ('COMMA', r','),            # ,
            ('PCOMMA', r';'),           # ;
            ('EQ', r'=='),              # ==
            ('NE', r'!='),              # !=
            ('LE', r'<='),              # <=
            ('GE', r'>='),              # >=
            ('OR', r'\|\|'),            # ||
            ('AND', r'&&'),             # &&
            ('ATTR', r'\='),            # =
            ('LT', r'<'),               # <
            ('GT', r'>'),                           # >
            ('PLUS', r'\+'),                        # +
            ('MINUS', r'-'),                        # -
            ('COMMENT_LINE', r'\/\/'),              # //
            ('COMMENT_START', r'\/\*'),             # /*
            ('COMMENT_END', r'\*\/'),               # */
            ('MULT', r'\*'),                        # *
            ('DIV', r'\/'),                         # /
            ('ID', r'[a-zA-Z]\w*'),                 # IDENTIFIERS
            ('FLOAT_CONST', r'\d(\d)*\.\d(\d)*'),   # FLOAT
            ('INTEGER_CONST', r'\d(\d)*'),          # INT
            ('NEWLINE', r'\n'),                     # NEW LINE
            ('SKIP', r'[ \t]+'),                    # SPACE and TABS
            ('MISMATCH', r'.'),                     # ANOTHER CHARACTER
        ]


    def tokenize(self, code):
        

        tokens_join = '|'.join('(?P<%s>%s)' % x for x in self.rules)
        lin_start = 0

        # Lists of output for the program

        row = []
        

        # It analyzes the code to find the lexemes and their respective Tokens
        for m in re.finditer(tokens_join, code):
            token_type = m.lastgroup
            token_lexeme = m.group(token_type)
            if token_type == 'NEWLINE':
                lin_start = m.end()
                self.lin_num += 1
            
            if token_type == 'SKIP':
                continue
            elif token_type == 'MISMATCH':
                self.log.print("{} unexpected on line {}".format(token_lexeme, self.lin_num))
                return Error(errCl = Classes.FILE_HAS_ERROR, 
                         errTp = Types.LEXICAL_ANALYZER_ERROR, 
                         FileName = self.file, 
                         FileLine = "",
                         CharacterNumber = 0)
            else:
                col = m.start() - lin_start
                row.append(self.lin_num)
                # To print information about a Token
                self.tokens+=[(token_type, token_lexeme, self.lin_num, col)]
        return None

    def getTokens(self):
         return self.tokens

    def process(self, fileName):
        self.name = fileName
        with open(fileName,"r") as inFile:
            while True:
                line = inFile.readline()
                if not line:
                    break
                isError = self.tokenize(line)        
                if isError is not None:
                    return isError

    def CommentRemover(self):
        rettokens = []
        for i,token in enumerate(self.tokens):
            if token[0] == 'COMMENT_LINE':
                for j,t in enumerate(self.tokens[i:]):
                    if t[0] == 'NEWLINE':
                        break
                del self.tokens[i:i+j]
            elif token[0] == 'COMMENT_START':
                for j,t in enumerate(self.tokens[i:]):
                    if t[0] == 'COMMENT_END':
                        break
                del self.tokens[i:i+j]
            else:
                rettokens.append(token)
        return rettokens                

    def ImportRemover(self):
        currImport = None
        endPos = len(self.tokens)
        self.log.print("tokens size:{}".format(len(self.tokens)))
        i = 0
        while i < endPos:
            if self.tokens[i][0] == 'IMPORT':
                currImport = i
            if self.tokens[i][0] == 'NEWLINE' and currImport is not None:
                fileName = self.parseImport(self.tokens[currImport:i])
                del self.tokens[currImport:i+1]
                endPos = len(self.tokens)
                i = i - (i+1-currImport)
                currImport = None
                self.log.print("file:{}".format(fileName))
            i = i+1

    
    def parseImport(self, tokens):
        
        currQuotes = None
        ret = ""
        for i,token in enumerate(tokens):
            if token[0] == "QUOTES" and currQuotes is None:
                currQuotes = i
            if token[0] != "QUOTES" and currQuotes is not None:
                ret+=token[1]
        return ret      
    
    def __str__(self):
        return "{}".format(self.tokens)