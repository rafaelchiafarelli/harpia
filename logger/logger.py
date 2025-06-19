## logger will be the regular console output for the project.
## features are:
"""
* regular console output
* specific file output
"""
import inspect


class logger():
    def __init__(self, outFile, moduleName) -> None:
        self.moduleName = moduleName
        self.outFile = outFile
        

    def print(self,msg):
        caller = inspect.getframeinfo(inspect.stack()[1][0])
        outMsg = "[" + self.moduleName + "]:" + " line:" + str(caller.lineno) + " - " + msg

        if self.outFile is None:
            print(outMsg)