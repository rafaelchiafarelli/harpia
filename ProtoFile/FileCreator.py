#get one message and create one proto, one .message and one .variables files
import os
from Logger.logger import logger
from Util.util import readFromTemplate, write_if_different
PROTO_EXT = ".proto"
MESSAGE_EXT = ".message"
VARIABLES_EXT = ".variables"

# Java's protoc plugin packs every message declared in one .proto into a
# single outer wrapper class by default. harpia's convention is already one
# message per .proto (hash-qualified filename), so without this option the
# Java target would nest every generated class inside a wrapper, unlike every
# other target -- see Initiatives/multi-language-targets/thread-1-java-target
# (session J.1). Both options are standard descriptor.proto FileOptions,
# ignored by every non-Java protoc backend, so emitting them unconditionally
# is safe for the C++ target too. One flat package for now -- there's no
# per-project/per-namespace concept in the emitted .proto to key off of.
# Flagged, not fixed: a flat package means two messages with the SAME NAME
# from two different root-file hashes would collide as Java classes (unlike
# their .proto filenames, which stay hash-qualified and never collide) --
# a latent multi-root risk, not a bug in today's single-root pipeline.
JAVA_PACKAGE = "com.harpia.generated"

class FileCreator():
    def __init__(self, message, imports, dest, compliance=None) -> None:
        self.compliance = compliance
        self.message = message
        self.fileName = "{}_{}.proto".format(message.name,message.md5Hash)
        self.gRPCfileName = "{}_{}_service.proto".format(message.name,message.md5Hash)
        self.modifierName = "{}_{}_modifier.message".format(message.name,message.md5Hash)
        self.accessName = "{}_{}_access.variable".format(message.name,message.md5Hash)
        self.tableName = "{}_{}_table.sql".format(message.name,message.md5Hash)
        self.tableAccess = "{}_{}_encrypted.pswd".format(message.name,message.md5Hash)
        self.imports = imports
        self.data = ""
        self.modifierData = []
        self.accessData = []
        self.dataBaseData = ""
        self.dataBaseAccess = {}
        self.destination = dest
        self.messageData = ""
        self.gRPCData = ""
        self.log = logger(outFile=None, moduleName="FileCreator")

    # proto3 type name for a harpia type token. Primitives are normalized
    # (the lexer keeps lexemes like 'int' or 'string ' that aren't valid proto
    # types); anything else (a composed message/enum) uses its name.
    _PROTO_PRIMITIVES = {"INT32": "int32", "INT64": "int64",
                         "FLOAT": "float", "STRING": "string"}

    def protoType(self, typeToken):
        return self._PROTO_PRIMITIVES.get(typeToken[0], typeToken[1])

    def Process(self):
        #create the proto file
        
        protoData = "syntax = \"proto3\";\n"
        protoData += "option java_multiple_files = true;\n"
        protoData += "option java_package = \"{}\";\n".format(JAVA_PACKAGE)
        for dep in self.imports:
            protoData+="import \"{}\"\n".format(dep)
        protoData+="\n"
        if self.message.dependency is not None:
            # dedup by target type name: a message may reference the same composed
            # type from more than one field (e.g. a singular FK and a repeated FK),
            # but protoc rejects a .proto that imports the same file twice.
            seenDeps = set()
            for dep in self.message.dependency:
                if dep[1] in seenDeps:
                    continue
                seenDeps.add(dep[1])
                protoData+="import \"{}/{}_{}.proto\";\n".format("protofiles",dep[1],self.message.md5Hash)
        
        if self.message.isEnum == False:
            protoData+="message {} {{\n".format(self.message.name)
            if self.message.tableName is not None:
                self.dataBaseData+=self.message.tableName
            self.dataBaseData+="\n"
            if self.message.visibility is not None:
                self.dataBaseData+=self.message.visibility

                if self.message.visibility == "PRIVATE":
                    self.dataBaseAccess["user"] = "{}".format(self.message.name)
                    self.dataBaseAccess["pswrd"] = "{}".format(self.message.md5Hash)

            self.dataBaseData+="\n"
            if self.message.variables is not None:
                for v in self.message.variables:
                    if v.typeMap:
                        # map<K,V>: typeMap holds the key/value type tokens.
                        # var.type alone is unreliable here -- the parser
                        # overwrites it with the last primitive seen inside the
                        # angle brackets, so emit from typeMap instead.
                        keyType = self.protoType(v.typeMap[0])
                        valType = self.protoType(v.typeMap[1])
                        protoData+="map<{}, {}> {} = {};\n".format(
                            keyType, valType, v.name, v.index)
                    else:
                        mods = v.modifiers or []
                        isRepeated = any(m[0] == 'REPETEABLE' for m in mods)
                        if isRepeated:
                            # proto3 forbids "optional repeated" -- repeated
                            # already has its own presence signal (an empty
                            # list), so REPETEABLE wins over OPTIONAL here.
                            prefix = "repeated "
                        elif any(m[0] == 'OPTIONAL' for m in mods):
                            # emits proto3's `optional` keyword, giving the
                            # field real explicit-presence tracking (a
                            # generated has_<field>() distinct from the
                            # zero-value default) instead of Harpia's
                            # OPTIONAL modifier being a no-op past the lexer
                            # -- see plans/message-versioning.md S4.
                            prefix = "optional "
                        else:
                            prefix = ""
                        protoData+="{}{} {} = {};\n".format(
                            prefix, self.protoType(v.type), v.name, v.index)
                    if len(v.modifiers) != 0:
                        self.accessData.append((v.name,v.modifiers))

# now we create the access protos. 
# one proto will have the variables and other protos will have the functions.
    # gRPC -- proto name will be the name of the original message + "Service";
        # several functions that will receive the message, do something with it and return OK or ERROR according to spec
            # one function that receives the message and return the errorCode.
            # one function per variable inside of the message and return OK or ERROR
            # one function that 
    # database access (CRUDL functions) ## this will have another layer. The database access.
        # we will have create, read, update, delete and list functions. 
            # "Create": one function with no parameters that creates a new entry in the database with the variables of the message as parameters. It will return OK or ERROR according to spec.
            # "Read": one function with no parameters that reads an entry from the database with the variables of the message as parameters. It will return OK or ERROR according to spec.
            # "Update": one function with no parameters that updates an entry in the database with the variables of the message as parameters. It will return OK or ERROR according to spec.
            # "Delete": one function with no parameters that deletes an entry from the database with the variables of the message as parameters. It will return OK or ERROR according to spec.
            # "List": one function with no parameters that lists all the entries in the database with the variables of the message as parameters. It will return OK or ERROR according to spec.
    # callback have 2 protos, one for the registering side and another for the calling the callback side.
        # register callback B1;                     --->            registered callback caller (not the B1, but the caller)
        # B1 is kept                                
        # callback function is called               <---            call the callback of the registered caller with the message as a parameter
        # B1 is called in a safe way;
        # proto 1 (registering side) will have the function to register the callback. The signature here is a function that receives a function as paremeter (the callback that will be called).
            # the alert to update of the database. 
            # the alert to a specific update of a specific variable in the database. This is going to receive the message as a parameter.
        # proto 2 (calling side) will have the function to call the callback.
            

        # streaming functions
        else:
            #create an Enum type
            protoData+="enum {} {{\n".format(self.message.name)
            if self.message.variables is not None: 
                for v in self.message.variables:
                    protoData+="{} = {};\n".format(v[0],v[1])
        
        protoData+="}\n"
        self.messageData = "{}".format(protoData)
        
        protoService = readFromTemplate("Service.proto", self.message.name)
        #self.log.print("protoService: {}".format(protoService))
        protoService = protoService.replace("%USER_MESSAGE_FILE_NAME%", self.fileName)
        self.gRPCData = "{}".format(protoService)
        
        if self.message.access_modifiers is not None:
            for modifier in self.message.access_modifiers:
                self.modifierData.append(modifier)


    def save(self, fileFolder = None):
        if fileFolder == None:
            messagePath = "{}/proto/protofiles/{}".format(self.destination,self.fileName)
            gRPCPath = "{}/proto/protofiles/{}".format(self.destination,self.gRPCfileName)
            messageModifierPath = "{}/modifier/{}".format(self.destination,self.modifierName)
            accessModifierPath = "{}/access_modifier/{}".format(self.destination,self.accessName)
            dataBaseAccessPath = "{}/database_access/{}".format(self.destination,self.tableAccess)
        else:
            messagePath = "{}/proto/protofiles/{}".format(fileFolder,self.fileName)
            gRPCPath = "{}/proto/protofiles/{}".format(fileFolder,self.gRPCfileName)
            messageModifierPath = "{}/modifier/{}".format(fileFolder,self.modifierName)
            accessModifierPath = "{}/access_modifier/{}".format(fileFolder,self.accessName)
            dataBaseAccessPath = "{}/database_access/{}".format(fileFolder,self.tableAccess)

        write_if_different(messagePath, self.messageData)
        write_if_different(gRPCPath, self.gRPCData)

        modifierData = ""
        for modifier in self.modifierData:
            modifierData += "{}\n".format(modifier.__str__())
        write_if_different(messageModifierPath, modifierData)

        accessModifierData = ""
        for access in self.accessData:
            accessModifierData += "{}:{};\n".format(access[0], access[1])
        write_if_different(accessModifierPath, accessModifierData)

        # database/<name>_<hash>_table.sql is NOT written here: SqlAdapter
        # (runs later in main.py, for every message including enums)
        # unconditionally supersedes it with the real schema, so writing a
        # stub here first just means every run touches this path twice --
        # defeating write-if-different for no benefit.

        if self.message.visibility == "PRIVATE":
            write_if_different(dataBaseAccessPath,
                               "{}".format(self.dataBaseAccess))
        elif os.path.exists(dataBaseAccessPath):
            # visibility changed away from PRIVATE since the last run -- this
            # sidecar's (name, hash) still matches a live message, so
            # Util.util.prune_stale_outputs wouldn't catch it as an orphan.
            os.remove(dataBaseAccessPath)
