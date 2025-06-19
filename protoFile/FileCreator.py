#get one message and create one proto, one .message and one .variables files
from Logger.logger import logger
PROTO_EXT = ".proto"
MESSAGE_EXT = ".message"
VARIABLES_EXT = ".variables"

class FileCreator():
    def __init__(self, message, imports, dest) -> None:
        self.message = message
        self.fileName = "{}_{}.proto".format(message.name,message.md5Hash)
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
        self.log = logger(outFile=None, moduleName="FileCreator")

    def Process(self):
        #create the proto file
        protoData = ""
        for dep in self.imports:
            protoData+="import \"{}\"\n".format(dep)
        protoData+="\n"
        if self.message.dependency is not None:
            for dep in self.message.dependency:
                protoData+="import \"{}_{}.proto\"\n".format(dep[1],self.message.md5Hash)

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
                    protoData+="{} {} = {};\n".format(v.type[1], v.name,v.index)
                    if len(v.modifiers) != 0:
                        
                        self.accessData.append((v.name,v.modifiers))

        else:
            #create an Enum type
            protoData+="enum {} {{\n".format(self.message.name)
            if self.message.variables is not None: 
                for v in self.message.variables:
                    protoData+="{} = {},\n".format(v[0],v[1])

        protoData+="}\n"
        self.messageData = "{}".format(protoData)
        if self.message.access_modifiers is not None:
            for modifier in self.message.access_modifiers:
                self.modifierData.append(modifier)


    def save(self, fileFolder = None):
        if fileFolder == None:
            messagePath = "{}/{}".format(self.destination,self.fileName)
            messageModifierPath = "{}/{}".format(self.destination,self.modifierName)
            accessModifierPath = "{}/{}".format(self.destination,self.accessName)
            dataBasePath = "{}/{}".format(self.destination,self.tableName)
            dataBaseAccessPath = "{}/{}".format(self.destination,self.tableAccess)
        else:
            messagePath = "{}/{}".format(fileFolder,self.fileName)
            messageModifierPath = "{}/{}".format(fileFolder,self.modifierName)
            accessModifierPath = "{}/{}".format(fileFolder,self.accessName)
            dataBasePath = "{}/{}".format(fileFolder,self.tableName)
            dataBaseAccessPath = "{}/{}".format(fileFolder,self.tableAccess)
        
        with open(messagePath, "w") as outFile:
            outFile.write(self.messageData)

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
