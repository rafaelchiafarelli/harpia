##util.py is a file that contains small functions and helpers to be genericly used. 
## specification is not recommended on this file.
import shutil
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


def copyTemplates(src, dest):
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dest, item)
        if os.path.isdir(s):
            copyTemplates(s, d)
        else:
            if not os.path.exists(dest):
                os.makedirs(dest)
            if not os.path.exists(d) or os.stat(s).st_mtime - os.stat(d).st_mtime > 1:
                shutil.copy2(s, d)

def copyCMakeFiles(src, dest):
    mainCMakePathSrc = "{}/{}".format(src, "CMakeLists.txt")
    if not os.path.exists(dest):
        os.makedirs(dest)   
    if os.path.isfile(os.path.join(dest, "CMakeLists.txt")):
        os.remove(os.path.join(dest, "CMakeLists.txt"))
    shutil.copy(mainCMakePathSrc, dest)
    
    protoCMakePathSrc = "{}/{}".format(src, "proto/CMakeLists.txt")
    if not os.path.exists(os.path.join(dest, "proto")):
        os.makedirs(os.path.join(dest, "proto"))
    if os.path.isfile(os.path.join(dest,"proto","CMakeLists.txt")):
        os.remove(os.path.join(dest,"proto","CMakeLists.txt"))        
    shutil.copy(protoCMakePathSrc, os.path.join(dest, "proto"))
    
    serverCMakePathSrc = "{}/{}".format(src, "server_template/CMakeLists.txt")
    if not os.path.exists(os.path.join(dest, "server")):
        os.makedirs(os.path.join(dest, "server"))
    if os.path.isfile(os.path.join(dest,"server","CMakeLists.txt")):
        os.remove(os.path.join(dest,"server","CMakeLists.txt"))
    shutil.copy(serverCMakePathSrc, os.path.join(dest, "server"))
    
    clientCMakePathSrc = "{}/{}".format(src, "client_template/CMakeLists.txt")
    if not os.path.exists(os.path.join(dest, "client")):
        os.makedirs(os.path.join(dest, "client"))
    if os.path.isfile(os.path.join(dest,"client","CMakeLists.txt")):
        os.remove(os.path.join(dest,"client","CMakeLists.txt"))
    shutil.copy(clientCMakePathSrc, os.path.join(dest, "client"))
    

def copyServerClientTemplates(src, dest):
    serverName = "main.cpp"
    clientName = "main.cpp"
    serverTemplatePathSrc = "{}/server_template/src/{}".format(src, serverName)
    clientTemplatePathSrc = "{}/client_template/src/{}".format(src, clientName)
    if not os.path.exists(dest):
        os.makedirs(dest)   
    if not os.path.exists(os.path.join(dest, "server","src")):
        os.makedirs(os.path.join(dest, "server","src"))
    if not os.path.exists(os.path.join(dest, "client","src")):
        os.makedirs(os.path.join(dest, "client","src"))
        
    if os.path.isfile(os.path.join(dest,"server","src", serverName)):
        os.remove(os.path.join(dest, "server", "src", serverName))
    shutil.copy2(serverTemplatePathSrc, os.path.join(dest, "server", "src", serverName))
    
    if os.path.isfile(os.path.join(dest, "client", "src", clientName)):
        os.remove(os.path.join(dest, "client", "src", clientName))        
    shutil.copy2(clientTemplatePathSrc, os.path.join(dest, "client", "src", clientName))
                
def readFromTemplate(templateName, messageName):
    with open("./Assets/proto/protofiles/{}".format(templateName), "r") as f:
        data = f.read()
        data = data.replace("%USER_MESSAGE%", messageName)
        return data

def copyBasicProtos(src, dest):
    errorProto = os.path.join(src, "errorCode.proto")
    heartBeatProto = os.path.join(src, "heartBeat.proto")
    destination = os.path.join(dest,"proto","protofiles")
    shutil.copy2(errorProto, destination)
    shutil.copy2(heartBeatProto, destination)