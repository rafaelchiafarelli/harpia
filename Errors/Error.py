

from enum import Enum


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

class Classes(Enum):
    FOLDER_NOT_FOUND= 1
    FILE_NOT_FOUND= 2
    FILE_IS_LINK= 3
    FILE_HAS_ERROR= 4
    BRACES = 5
    MODIFIERS = 6

class Error:
    errType = Types
    errClass = Classes
    FileNme  = ""
    FileLine = ""
    CharacterNumber = 0
    
    def __init__(self, errCl, errTp, FileName = "", FileLine="", CharacterNumber=0) -> None:
        self.errType = errTp
        self.errClass = errCl
        self.FileNme = FileName
        self.FileLine = FileLine
        self.CharacterNumber = CharacterNumber
    def __str__(self) -> str:
        return "ErrorType:" + self.errType.name + " ErrorClass:" + self.errClass.name + " at File:" + self.FileNme + ", line:" + str(self.FileLine) + " and Character:" + str(self.CharacterNumber)