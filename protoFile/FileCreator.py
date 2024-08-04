#get one message and create one proto, one .message and one .variables files
from logger.logger import logger
PROTO_EXT = ".proto"
MESSAGE_EXT = ".message"
VARIABLES_EXT = ".variables"

class FileCreator():
    def __init__(self, message, imports) -> None:
        self.message = message
        self.fileName = "{}_{}.proto".format(message.name,message.md5Hash)
        self.imports = imports
        self.filePath = ""
        self.data = ""
        self.log = logger(outFile=None, moduleName="FileCreator")
    def Process(self):
        #create the proto file
        protoData = ""
        for dep in self.imports:
            protoData+="import {}\n".format(dep)
        protoData+="\n"
        if self.message.dependency is not None:
            for dep in self.message.dependency:
                protoData+="import \"{}_{}.proto\"\n".format(dep[1],self.message.md5Hash)

        if self.message.isEnum == False:
            protoData+="message {} {{\n".format(self.message.name)
            if self.message.variables is not None:
                for v in self.message.variables:
                    protoData+="{} {} = {};\n".format(v.type[1], v.name,v.index)
        else:
            #create an Enum type
            protoData+="enum {} {{\n".format(self.message.name)
            if self.message.variables is not None: 
                for v in self.message.variables:
                    self.log.print("{}".format(v.__str__()))  
                    protoData+="{} = {},\n".format(v[0],v[1])

        protoData+="}\n"
        self.data = "{}".format(protoData)

    def save(self, fileFolder = None):
        self.log.print("{}".format(fileFolder))
        if fileFolder == None:
            self.filePath = "./build/{}".format(self.fileName)
        else:
            self.filePath = "{}/{}".format(fileFolder,self.fileName)
        self.log.print("{}".format(self.filePath))
        with open(self.filePath, "w") as outFile:
            outFile.write(self.data)

