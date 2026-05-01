#get one message and create one proto, one .message and one .variables files
from Logger.logger import logger
from Util.util import readFromTemplate
PROTO_EXT = ".proto"
MESSAGE_EXT = ".message"
VARIABLES_EXT = ".variables"

class FileCreator():
    def __init__(self, message, imports, dest) -> None:
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

    def Process(self):
        #create the proto file
        
        protoData = "syntax = \"proto3\";"
        for dep in self.imports:
            protoData+="import \"{}\"\n".format(dep)
        protoData+="\n"
        if self.message.dependency is not None:
            for dep in self.message.dependency:
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
                    varType = "err"
                    if v.type[0] == "INT32":
                        varType = 'int32'
                    elif v.type[0] == "INT64":
                        varType = "int64"
                    else:
                        varType = v.type[1]
                    protoData+="{} {} = {};\n".format(varType, v.name,v.index)
                    if len(v.modifiers) != 0:
                        self.accessData.append((v.name,v.modifiers))

# now we create the access protos. 
# one proto will have the variables and other proto will have the functions.
    # for the porpose of the harpia project, we can put all the interfaces into a single proto file, and enable each with some clevor preprocessor directives.
    # it will work for c++. Other languages will have to be adapted.
    # the template C++ will have the preprocessor directives to enable the different interfaces, that will be replaced by the FileCreator.
    # the interfaces that we will have are:
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
            dataBasePath = "{}/database/{}".format(self.destination,self.tableName)
            dataBaseAccessPath = "{}/database_access/{}".format(self.destination,self.tableAccess)
        else:
            messagePath = "{}/proto/protofiles/{}".format(fileFolder,self.fileName)
            gRPCPath = "{}/proto/protofiles/{}".format(fileFolder,self.gRPCfileName)
            messageModifierPath = "{}/modifier/{}".format(fileFolder,self.modifierName)
            accessModifierPath = "{}/access_modifier/{}".format(fileFolder,self.accessName)
            dataBasePath = "{}/database/{}".format(fileFolder,self.tableName)
            dataBaseAccessPath = "{}/database_access/{}".format(fileFolder,self.tableAccess)
        
        with open(messagePath, "w") as outFile:
            outFile.write(self.messageData)

        with open(gRPCPath, "w") as outFile:
            outFile.write(self.gRPCData)

        with open(messageModifierPath, 'w') as outFile:
            modifierData=""
            for modifier in self.modifierData:
                modifierData+="{}\n".format(modifier.__str__())
            outFile.write(modifierData)

        with open(accessModifierPath, 'w') as outFile:
            accessModifierData=""
            for access in self.accessData:
                accessModifierData+="{}:{};\n".format(access[0],access[1])
            outFile.write(accessModifierData)
            
        with open(dataBasePath, 'w') as outFile:
            outFile.write(self.dataBaseData)      
              
        if self.message.visibility is not None:
            if self.message.visibility == "PRIVATE":
                with open(dataBaseAccessPath, 'w') as outFile:
                    outFile.write("{}".format(self.dataBaseAccess))
