##util.py is a file that contains small functions and helpers to be genericly used. 
## specification is not recommended on this file.
import string
import os
from Errors.Error import Error, Types, Classes
import hashlib

class switch(object):
    value = None
    def __new__(class_, value):
        class_.value = value
        return True

    def case(*args):
        return any((arg == switch.value for arg in args))


def isascii(s):
    """Check if the characters in string s are in ASCII, U+0-U+7F."""
    
    if not s:
        return True,0
    if len(s) != len(s.encode()):
        count=0
        for c in s:
            if c not in string.ascii_letters:
                return False,count
            count+=1
    return True,0


def isFileInFolders(folders, file):
    for folder in folders:
        if not os.path.exists(folder):
            return False, Error(errCl = Classes.FILE_HAS_ERROR, 
                        errTp = Types.IMPORT_INCOMPLETE_ERROR, 
                        FileName = file, 
                        FileLine = "",
                        CharacterNumber = 0)
        else:
            fullPath = "{}/{}".format(folder,file)
        if os.path.isfile(fullPath):
            return True, fullPath
        
    return False,Error(errCl = Classes.FILE_HAS_ERROR, 
                        errTp = Types.IMPORT_INCOMPLETE_ERROR, 
                        FileName = file, 
                        FileLine = "",
                        CharacterNumber = 0)

