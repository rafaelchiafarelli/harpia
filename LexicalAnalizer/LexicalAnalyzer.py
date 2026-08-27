import re
from Logger.logger import logger
from Errors.Error import Error, Types, Classes

## LexicalAnalyzer should only tokenize the files 
class LexicalAnalyzer:
    log = logger(outFile=None, moduleName="LexicalAnalizer" )    
    # Token row
    lin_num = 1
    tokens = []
    def __init__(self, compliance=None) -> None:
        self.compliance = compliance
        self.name = "empty"
        # Bare-word keyword rules (INT32/INT64/FLOAT/STRING/MAP/IMPORT/
        # REPETEABLE/PAGINATION) are anchored with a trailing \b. The rules are
        # joined into one alternation regex (see tokenize()) and Python's re
        # alternation is leftmost-alternative-wins, not longest-match: without
        # the boundary, `int` matched the start of `integrator_link_state`,
        # lexing it as INT32("int") + ID("egrator_link_state") and failing with
        # NO_NAME_IN_MESSAGE. \b makes each rule match only when the keyword is
        # not immediately followed by another word character. The modifier
        # keywords below (`enum `, `stream `, ... `message `) are instead
        # protected by a required trailing space, so they need no \b.
        self.rules = [
            ('IMPORT', r'import\b'),
            ('QUOTES', r'\"'),
            ('POINT',r'\.'),
            ('ENUM', r'enum '),
            ('STREAM',r'stream '),
            ('PULL',r'pull '),
            ('PUSH',r'push '),
            ('EVENT',r'event '),
            ('PUSHPULL',r'pushpull '),
            # message-type criticality modifier (sensitive-data design rules
            # §0, the *criticality* axis -- independent of PHI's confidentiality
            # axis). A keyword-only modifier that sits in the same slot as the
            # transport kinds above (before `message `), trailing space so it
            # never matches a bare identifier or `criticality`. Flag only: no
            # delivery-guarantee machinery lands with this token -- that is
            # Phase 3 of sensitive-data-implementation-roadmap.md. Consumed by
            # Message/Message.py -> Message.is_critical, the same way PHI ->
            # variable.is_phi.
            ('CRITICAL', r'critical '),
            ('MESSAGE',r'message '),
            # sensitive-field modifier (Foundation F2, confidentiality axis --
            # see Initiatives/medical_devices/harpia_sensitive_data_design_rules.md
            # §0). Same category as OPTIONAL/REQUIRED/UNIQUE below: a
            # keyword-only modifier, no value, flag only -- no encryption/
            # redaction/audit logic lands with this token.
            ('PHI', r'phi '),
            ("OPTIONAL", r'optional '),
            ('REPETEABLE',r'repeteable\b'),
            ('PAGINATION',r'pagination\b'),
            ('REQUIRED',r'required '),
            ('UNIQUE',r'unique '),
            ('RENAMED_FROM', r'renamed_from\[\s*[a-zA-Z]\w*\s*\]'),
            ('MAP', r'map\b'),
            # INT64 still precedes INT32 (and both are now \b-anchored, above):
            # rules are joined into one alternation regex (see tokenize()
            # below) and Python's re alternation is leftmost-alternative-wins,
            # not longest-match -- with INT32's `int` listed first and no
            # boundary, every `int64` in a .harpia file silently lexed as
            # INT32("int") + a stray INTEGER_CONST("64"), downgrading every
            # declared int64 field to int32 with no error. Caught 2026-08-25 by
            # UnitTests/test_java_db_crudl.py's
            # test_bind_extract_roundtrip_per_supported_type -- the only place
            # in this repo's entire test suite that ever declared an int64
            # field, since no HarpiaTest fixture uses one. With `int\b` the
            # ordering is no longer load-bearing (`int\b` cannot match inside
            # `int64`), but leave it as defence in depth.
            ('INT64', r'int64\b'),            # int64
            ('INT32', r'int\b'),            # int32
            ('FLOAT', r'float\b'),        # float
            ('STRING', r'string\b'),        # string
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
                         FileName = self.name,
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