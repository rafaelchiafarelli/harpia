## pre_lexical will read the selected file and make all the pre-lex operations
import os
from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import isascii, isFileInFolders
import shutil
import hashlib

class pre_lex:
    def __init__(self, folders, file,dest):
        self.log = logger(outFile=None, moduleName="pre-lexical")
        self.folders = []
        self.file = ""
        self.files = []
        if folders is None:
            self.folders.append(os.getcwd())
        else:
            self.folders = folders
        self.md5hash = None
        self.file = file
        self.destination = dest
        if not os.path.exists(dest):
            os.makedirs(dest)
    def process(self):
        
        isFile,file = isFileInFolders(self.folders,self.file)
        if isFile is not True:
            #if it is not a File, so it is an error and we must return it
            return file
        all_data = ""
        with open(file) as f:
            line = 0
            open_parentesis=0
            close_parentesis=0
            open_braquets=0
            close_braquets=0
            open_comment=0
            close_comment=0
            open_square=0
            close_square=0
            
            while True:

                raw_data = f.readline()
                ##end of file
                if not raw_data:
                    break
                all_data += raw_data
                ##remove non printable characters, such as "new line" and "space"
                raw_data = raw_data.strip()
                
                ##check if it is ascii
                r,c = isascii(raw_data)
                if not r:
                    return Error(errCl=Classes.FILE_HAS_ERROR, 
                                 errTp=Types.NON_ASCII_CHAR, 
                                 FileName=self.file,
                                 FileLine=line,
                                 CharacterNumber=c)
                line+=1

                ##add all the special characters
                open_parentesis += raw_data.count("(")
                close_parentesis += raw_data.count(")")
                open_braquets += raw_data.count("{")
                close_braquets += raw_data.count("}")
                open_comment += raw_data.count("/*")
                close_comment += raw_data.count("*/")
                open_square += raw_data.count("[")
                close_square += raw_data.count("]")
                
                if raw_data.startswith("import"):
                    impLine = raw_data.split(" ")
                    if len(impLine)<2:
                        return Error(errCl=Classes.FILE_HAS_ERROR, 
                                 errTp=Types.IMPORT_INCOMPLETE_ERROR, 
                                 FileName=self.file,
                                 FileLine=line,
                                 CharacterNumber=c)
                    impFile = impLine[1]
                    if not isFileInFolders(self.folders,impFile):
                        return Error(errCl=Classes.FILE_HAS_ERROR, 
                                 errTp=Types.IMPORT_NOT_FOUND, 
                                 FileName=self.file,
                                 FileLine=line,
                                 CharacterNumber=c)
            ##return error if found problems
            if open_parentesis != close_parentesis:
                return Error(errCl = Classes.FILE_HAS_ERROR, 
                         errTp = Types.PARENTESIS_COUNT_ERROR, 
                         FileName = self.file, 
                         FileLine = "",
                         CharacterNumber = 0)                
            if open_square != close_square:
                return Error(errCl = Classes.FILE_HAS_ERROR, 
                         errTp = Types.SQUARE_COUNT_ERROR, 
                         FileName = self.file, 
                         FileLine = "",
                         CharacterNumber = 0)                
            if open_braquets != close_braquets:
                return Error(errCl = Classes.FILE_HAS_ERROR, 
                         errTp = Types.BRAKETS_COUNT_ERROR, 
                         FileName = self.file, 
                         FileLine = "",
                         CharacterNumber = 0)
            if open_comment != close_comment:
                return Error(errCl = Classes.FILE_HAS_ERROR, 
                         errTp = Types.COMMENTS_COUNT_ERROR, 
                         FileName = self.file, 
                         FileLine = "",
                         CharacterNumber = 0)
        
        if all_data != "":
            
            self.md5hash = hashlib.md5(all_data.encode()).hexdigest()

        self.log.print("pre lexic complete")
        return None
    
    def getHash(self):
        return self.md5hash
