##util.py is a file that contains small functions and helpers to be genericly used.
## specification is not recommended on this file.
import shutil
import string
import os
import json as _json
from Errors.Error import Error, Types, Classes
import hashlib

_HIDDEN_PREFIXES = ("ID_", "STATUS_", "ERROR_", "ORIGINATOR")
_DEMO_SCALARS = {"STRING", "INT32", "INT64", "FLOAT"}


def chooseDemo(messages):
    """Pick the message that drives the end-to-end demo and a sample payload.

    The demo client PUSHes and the server PULLs, so the message must have a
    push/pull transport -- i.e. a PUSH or PULL access modifier. Returns a
    substitution dict {DEMO_MESSAGE, DEMO_HASH, DEMO_SAMPLE_JSON} for the first
    such message, or None if no message is push/pull capable.
    """
    for msg in messages:
        if getattr(msg, "isEnum", False):
            continue
        mods = {m[0] for m in (getattr(msg, "access_modifiers", None) or [])}
        if not (mods & {"PUSH", "PULL"}):
            continue
        return {
            "DEMO_MESSAGE": msg.name,
            "DEMO_HASH": str(msg.md5Hash),
            "DEMO_SAMPLE_JSON": _sampleJson(msg),
        }
    return None


def _sampleJson(msg):
    """A minimal valid JSON payload: the first plain scalar user field set to a
    demo value (so a real value visibly crosses the wire). Falls back to {}."""
    for v in (msg.variables or []):
        if v.name.startswith(_HIDDEN_PREFIXES):
            continue
        if getattr(v, "typeMap", None):  # map field
            continue
        if v.type[0] not in _DEMO_SCALARS:  # composed / message ref
            continue
        value = "harpia-demo" if v.type[0] == "STRING" else 7
        return _json.dumps({v.name: value})
    return "{}"

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
    

def copyServerClientTemplates(src, dest, demo=None):
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

    serverDest = os.path.join(dest, "server", "src", serverName)
    clientDest = os.path.join(dest, "client", "src", clientName)
    if os.path.isfile(serverDest):
        os.remove(serverDest)
    if os.path.isfile(clientDest):
        os.remove(clientDest)

    _emitTemplate(serverTemplatePathSrc, serverDest, demo)
    _emitTemplate(clientTemplatePathSrc, clientDest, demo)


def _emitTemplate(srcPath, destPath, demo):
    """Write the server/client main.cpp, substituting the demo placeholders.

    If there is no push/pull message to demo (demo is None) the placeholders
    can't resolve, so emit a tiny stub that still compiles instead."""
    if demo is None:
        with open(destPath, "w") as out:
            out.write("#include <iostream>\n"
                      "int main() {\n"
                      "    std::cout << \"harpia: no push/pull message to demo\\n\";\n"
                      "    return 0;\n"
                      "}\n")
        return
    with open(srcPath, "r") as f:
        data = f.read()
    for key, value in demo.items():
        data = data.replace("%{}%".format(key), value)
    with open(destPath, "w") as out:
        out.write(data)
                
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