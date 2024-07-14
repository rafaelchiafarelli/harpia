

from enum import Enum
import inspect

class Types(Enum):
    NOTHING_TO_REPORT = 1
    LACK_OF_CLOSING_PRENTESIS = 2
    LACK_OF_OPENING_PARENTESIS = 3
    NON_ASCII_CHAR = 4
    PARENTESIS_COUNT_ERROR = 5
    BRAKETS_COUNT_ERROR = 6
    SQUARE_COUNT_ERROR = 7
    COMMENTS_COUNT_ERROR = 8
    IMPORT_INCOMPLETE_ERROR = 9
    IMPORT_NOT_FOUND = 10
    LEFT_BRACE_NOT_FOUND = 11
    RIGHT_BRACE_NOT_FOUND = 12
    MESSAGE_NOT_TERMINATED = 13
    MODIFIERS_BAD_POSITIONED = 14
    VARTYPE_NOT_FOUND = 15
    MULTIPLE_INSTANCES_OF_MESSAGES = 16
    MESSAGES_INSIDE_MESSAGES_ARE_NOT_ALLOWED = 17
    MULTIPLE_INSTANCES_OF_INDEX = 18
    MALFORMED_PAGINATION = 19
    MALFORMED_REPETEABLE = 20
    MALFORMED_MAP = 21
    VARTYPE_NOT_DEFINED = 22
    REGEX_NOT_FOUND = 23
    VARIABLE_WITHOUT_INDEX = 24
    NO_NAME_IN_MESSAGE = 25
    NO_MESSAGE_INITIALYSER = 26

class Classes(Enum):
    FOLDER_NOT_FOUND= 1
    FILE_NOT_FOUND= 2
    FILE_IS_LINK= 3
    FILE_HAS_ERROR= 4
    BRACES = 5
    MODIFIERS = 6
    VARTYPES = 7
    MESSAGES = 8
    REGEX = 9

class Error:
    errType = Types
    errClass = Classes
    FileNme  = ""
    FileLine = ""
    CharacterNumber = 0
    
    def __init__(self, errCl, errTp, FileName = "", FileLine="", CharacterNumber=0) -> None:
        caller = inspect.getframeinfo(inspect.stack()[1][0])
        self.outMsg = "[" + caller.filename + "]:"  " line:" + str(caller.lineno)

        self.errType = errTp
        self.errClass = errCl
        self.FileNme = FileName
        self.FileLine = FileLine
        self.CharacterNumber = CharacterNumber
    def __str__(self) -> str:
        return self.outMsg + " ErrorType:" + self.errType.name + " ErrorClass:" + self.errClass.name + " at File:" + self.FileNme + ", line:" + str(self.FileLine) + " and Character:" + str(self.CharacterNumber)