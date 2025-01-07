## pre_lexical will read the selected file and make all the pre-lex operations
import os
from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import isascii, isFileInFolders
import shutil
import hashlib

class pre_lex:
    def __init__(self, folders, file,dest, includeFolder):
        self.log = logger(outFile=None, moduleName="pre-lexical")
        self.folders = folders
        self.file = file
        self.includeFolder = []
        self.includeFolder.append(os.getcwd())

        if os.path.exists(file):
            self.includeFolder.append(os.path.dirname(file))

        if includeFolder is not None:
            self.includeFolder.append(includeFolder)
        
        self.md5hash = None
        
        self.destination = dest
        self.listOfHarpiaImports = []
        if not os.path.exists(dest):
            os.makedirs(dest)

    def process(self):
        
        isFile,file = isFileInFolders(self.includeFolder,self.file)
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
                
                #check for import files 
                if raw_data.startswith("import") and raw_data.endswith(";"):
                    impLine = raw_data.split(" ")
                    if len(impLine)<2:
                        return Error(errCl=Classes.FILE_HAS_ERROR, 
                                 errTp=Types.IMPORT_INCOMPLETE_ERROR, 
                                 FileName=self.file,
                                 FileLine=line,
                                 CharacterNumber=c)
                    impFile = impLine[1].strip("\";")
                    isFileInFolder, err = isFileInFolders(self.includeFolder,impFile)
                    if isFileInFolder is False:
                        # there is an error, must return the error
                        return err
                    else:
                        # there is no error, so it is a file (absolute path of a file)

                        self.listOfHarpiaImports.append(err)

                elif raw_data.startswith("import") and not raw_data.endswith(";"):
                    return Error(errCl=Classes.FILE_HAS_ERROR, 
                                 errTp=Types.IMPORT_INCOMPLETE_ERROR, 
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

        self.log.print("pre lexic for {} complete".format(self.file))
        return None
    
    def getListOfHarpias(self):
        return self.listOfHarpiaImports
    
    def getFile(self):
        return self.file
    
    def getHash(self):
        return self.md5hash

    
    def __str__(self) -> str:
        st = self.file
        if self.md5hash != None:
            st+= " {}".format(self.md5hash)
        else:
            st+= " no md5"
        if self.listOfHarpiaImports != None:
            st+= " {}".format(self.listOfHarpiaImports)
        return st