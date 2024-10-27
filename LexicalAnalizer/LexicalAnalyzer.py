import re
from Logger.logger import logger



class LexicalAnalyzer:
    log = logger(outFile=None, moduleName="LexicalAnalizer" )    
    # Token row
    lin_num = 1
    tokens = []
    def __init__(self) -> None:
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
            ('INT', r'int'),            # int
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
        token = []
        lexeme = []
        row = []
        column = []

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
                raise RuntimeError()
            else:
                col = m.start() - lin_start
                column.append(col)
                token.append(token_type)
                lexeme.append(token_lexeme)
                row.append(self.lin_num)
                # To print information about a Token
                self.tokens+=[(token_type, token_lexeme, self.lin_num, col)]

        return token, lexeme, row, column

    def getTokens(self):
         return self.tokens
