##util.py is a file that contains small functions and helpers to be genericly used.
## specification is not recommended on this file.
import filecmp
import shutil
import string
import os
import re
import json as _json
from Errors.Error import Error, Types, Classes
import hashlib

_HIDDEN_PREFIXES = ("ID_", "STATUS_", "ERROR_", "ORIGINATOR")
_DEMO_SCALARS = {"STRING", "INT32", "INT64", "FLOAT"}

# Harpia's generated-file naming convention: "<message name>_<root md5 hash>...".
# `prune_stale_outputs` uses this to tell a generated file from anything else
# in the output tree (CMakeLists.txt, vendored third_party/, ...).
_NAME_HASH_RE = re.compile(r'^([A-Za-z_]\w*)_([0-9a-f]{32})')
# Non-message-keyed but still hash-qualified filenames that must never be
# treated as orphans -- TestAdapter's single app-level test (app_<hash>_test.cpp).
_ALWAYS_VALID_BASENAMES = {"app"}


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
    # A path that already resolves to a file (absolute, or relative to cwd) is
    # taken as-is; only bare names (e.g. import "file1.harpia") need the folder
    # search below. This is what lets the input .harpia live anywhere on disk.
    if os.path.isfile(file):
        return True, file
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


def write_if_different(path, content):
    """Write content to path unless it's already there unchanged, so an
    unchanged generated file keeps its mtime -- lets a downstream cmake/make
    build treat it as unchanged too, instead of recompiling it on every
    regenerate just because the write gave it a fresh mtime."""
    if os.path.exists(path):
        with open(path, "r") as f:
            if f.read() == content:
                return False
    with open(path, "w") as f:
        f.write(content)
    return True


def copy_if_different(src, dst):
    """shutil.copy2, skipped (mtime preserved) when dst already matches src
    byte-for-byte -- same goal as write_if_different, for the static/vendored
    files that are copied rather than rendered."""
    if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
        return False
    shutil.copy2(src, dst)
    return True


def prune_stale_outputs(dest, current_hash, valid_names):
    """Remove generated files left behind by a message that was renamed or
    removed, or by a previous run against a different root-file hash --
    replaces the old blanket `shutil.rmtree(dest)` now that regeneration is
    write-if-different (see main.py). Only touches files matching harpia's
    own "<name>_<hash>..." naming convention; anything else (CMakeLists.txt,
    vendored third_party/, ...) is left alone.
    """
    for root, _dirs, files in os.walk(dest):
        for fn in files:
            m = _NAME_HASH_RE.match(fn)
            if not m:
                continue
            name, file_hash = m.group(1), m.group(2)
            if file_hash == current_hash and (
                    name in valid_names or name in _ALWAYS_VALID_BASENAMES):
                continue
            os.remove(os.path.join(root, fn))


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
    copy_if_different(mainCMakePathSrc, os.path.join(dest, "CMakeLists.txt"))

    protoCMakePathSrc = "{}/{}".format(src, "proto/CMakeLists.txt")
    if not os.path.exists(os.path.join(dest, "proto")):
        os.makedirs(os.path.join(dest, "proto"))
    copy_if_different(protoCMakePathSrc,
                       os.path.join(dest, "proto", "CMakeLists.txt"))

    serverCMakePathSrc = "{}/{}".format(src, "server_template/CMakeLists.txt")
    if not os.path.exists(os.path.join(dest, "server")):
        os.makedirs(os.path.join(dest, "server"))
    copy_if_different(serverCMakePathSrc,
                       os.path.join(dest, "server", "CMakeLists.txt"))

    clientCMakePathSrc = "{}/{}".format(src, "client_template/CMakeLists.txt")
    if not os.path.exists(os.path.join(dest, "client")):
        os.makedirs(os.path.join(dest, "client"))
    copy_if_different(clientCMakePathSrc,
                       os.path.join(dest, "client", "CMakeLists.txt"))
    

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

    _emitTemplate(serverTemplatePathSrc, serverDest, demo)
    _emitTemplate(clientTemplatePathSrc, clientDest, demo)


def _emitTemplate(srcPath, destPath, demo):
    """Write the server/client main.cpp, substituting the demo placeholders.

    If there is no push/pull message to demo (demo is None) the placeholders
    can't resolve, so emit a tiny stub that still compiles instead."""
    if demo is None:
        write_if_different(destPath,
            "#include <iostream>\n"
            "int main() {\n"
            "    std::cout << \"harpia: no push/pull message to demo\\n\";\n"
            "    return 0;\n"
            "}\n")
        return
    with open(srcPath, "r") as f:
        data = f.read()
    for key, value in demo.items():
        data = data.replace("%{}%".format(key), value)
    write_if_different(destPath, data)
                
def readFromTemplate(templateName, messageName):
    with open("./Assets/proto/protofiles/{}".format(templateName), "r") as f:
        data = f.read()
        data = data.replace("%USER_MESSAGE%", messageName)
        return data


def loadTemplate(callerFile, name):
    """Read a code-generator template from the 'templates' directory next to the
    calling module. Templates use Python str.format placeholders ({name}, {cls},
    ...); keep C++ braces escaped as {{ }} in the template files."""
    path = os.path.join(os.path.dirname(os.path.abspath(callerFile)),
                        "templates", name)
    with open(path, "r") as f:
        return f.read()

def copyBasicProtos(src, dest):
    errorProto = os.path.join(src, "errorCode.proto")
    heartBeatProto = os.path.join(src, "heartBeat.proto")
    destination = os.path.join(dest,"proto","protofiles")
    copy_if_different(errorProto, os.path.join(destination, "errorCode.proto"))
    copy_if_different(heartBeatProto, os.path.join(destination, "heartBeat.proto"))