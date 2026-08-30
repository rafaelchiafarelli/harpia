
##this is a container file that will have all caracteristics for the messages
import copy
from Message.Variables import Variables
from Message.EnumValues import EnumValues
from Message.FieldMap import freeze as freezeFieldNumbers
from Errors.Error import Types, Classes, Error
from Logger.logger import logger
class Message():
    log = None
    access_modifiers = None
    name = None
    variables = None
    availableMessages = None
    tableName = None
    visibility = None
    md5Hash = None
    dependency = None
    isEnum = False
    # sensitive-data design rules §0, criticality axis: True when the message
    # type carries the `critical` modifier. Message-type-level (never
    # per-field, never a payload value) and independent of any field's
    # `is_phi`. Flag only for now -- later stages read this instead of
    # re-scanning access_modifiers, same rationale as variable.is_phi.
    is_critical = False
    # dds-transport epic, task 1: True when the message type carries the `dds`
    # transport-selection modifier (ASTM F2761 / OpenICE-class bedside bus).
    # Message-type-level, independent of `is_critical` and of any field's
    # `is_phi`; composes with the other transport kinds (a `dds` message can
    # also be reachable over ZMQ/gRPC). Flag only for now -- the DdsAdapter,
    # QoS mapping and DDS-Security wiring that read this are tasks 2a/2b/3;
    # dedicated bool so they read it instead of re-scanning access_modifiers,
    # same rationale as is_critical / variable.is_phi.
    is_dds = False
    # events-callbacks epic, task 1: cache mode of the `event` message-type
    # modifier. None ⇔ no `event` modifier; "cached" for bare `event` or
    # `event[cached]` (cached is the standard when unspecified); "not-cached"
    # for `event[not-cached]`. Dedicated attribute so later stages read it
    # instead of re-parsing the EVENT token lexeme, same rationale as
    # is_critical / variable.is_phi. Flag only in the front end -- the
    # emitted .proto is identical regardless of the mode.
    event_cache_mode = None
    def __init__(self, fileName,availableMessages, md5Hash, compliance=None) -> None:

        self.compliance = compliance
        self.file = fileName
        self.availableMessages = availableMessages
        self.variables = []
        self.access_modifiers = []
        self.is_critical = False
        self.is_dds = False
        self.event_cache_mode = None
        self.log = logger(outFile=None, moduleName="Message")
        self.tableName = ""
        self.visibility = "PUBLIC"
        self.md5Hash = md5Hash


    def Process(self, tokens):
        startOfVariables = 0
        endOfVariables = 0
        rBracePosition = None
        curNewLine = None
        isOneToMany = None
        isEnum = False
        lastToken = ""
        for j,token in enumerate(tokens):
            if token[0] == 'NEWLINE':
                curNewLine = j
    
            if token[0] == "MESSAGE" or  token[0] == "ENUM":
                if token[0] == "ENUM":
                    isEnum = True

                if isEnum is False:
                    # tokens between the previous line break and `message` are
                    # the message-type modifiers (event/stream/pull/push/
                    # pushpull/critical). When the message is the very first
                    # thing in the token stream there is no preceding NEWLINE,
                    # so fall back to the start of the slice -- the old code
                    # forced curNewLine = j here, yielding tokens[j+1:j] (an
                    # empty range) and silently dropping a leading modifier.
                    modStart = 0 if curNewLine is None else curNewLine + 1
                    self.access_modifiers = tokens[modStart:j]
                    ##check if is a pull msg
                    for access in self.access_modifiers:
                        if access[0] == 'PULL' or access[0] == 'EVENT' or access[0] =='STREAM':
                            isOneToMany = True
                            break
                    ##criticality axis (sensitive-data design rules §0):
                    ##independent of the transport kind above, so a separate
                    ##scan -- `critical` can appear with or without event/
                    ##stream/push/pull.
                    for access in self.access_modifiers:
                        if access[0] == 'CRITICAL':
                            self.is_critical = True
                            break
                    ##transport-selection axis (dds-transport epic, task 1):
                    ##`dds` marks the message for a DDS bus. Independent of the
                    ##one-to-many transport kinds and of `critical`, so its own
                    ##scan -- `dds` can appear with or without any of them, in
                    ##any order. Flag only: it never sets isOneToMany, so a
                    ##`dds` message emits byte-identical .proto/DB output to the
                    ##same message without it (same guarantee phi/critical hold).
                    for access in self.access_modifiers:
                        if access[0] == 'DDS':
                            self.is_dds = True
                            break
                    ##events-callbacks epic task 1: cache mode rides in the
                    ##EVENT token lexeme (`event `, `event[cached] `,
                    ##`event[not-cached] `). Bare event == cached, the
                    ##standard when unspecified.
                    for access in self.access_modifiers:
                        if access[0] == 'EVENT':
                            self.event_cache_mode = (
                                'not-cached' if 'not-cached' in access[1]
                                else 'cached')
                            break
            if lastToken == "MESSAGE" or  lastToken == "ENUM":
                if token[0] == "ID":
                    self.name = token[1]
                    
                else:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3]) 
            lastToken = token[0]

            if token[0] == "LBRACE":
                startOfVariables=j+1
                if self.name is None:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3]) 
                
            if token[0] == "RBRACE":
                if startOfVariables is None:
                    return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_MESSAGE_INITIALYSER, 
                        FileName=self.file,
                        FileLine=token[2],
                        CharacterNumber=token[3])  
  
                if isEnum == False:
                    endOfVariables = j-1
                    v = Variables(filename=self.file,
                                tok=tokens[startOfVariables:endOfVariables],
                                composedVariables= self.availableMessages,
                                md5Hash=self.md5Hash,
                                isOneToMany=isOneToMany,
                                compliance=self.compliance)
                    ret = v.Process()
                    if ret != None:
                        return ret
                    if v.dependencies != None:
                        self.dependency = v.dependencies
                    self.variables = v.get()
                    freezeErr = freezeFieldNumbers(self.variables, self.file, self.name)
                    if freezeErr != None:
                        return freezeErr
                    rBracePosition = j

                else:
                    endOfVariables = j-1
                    
                    v = EnumValues(filename=self.file,
                                tok=tokens[startOfVariables:endOfVariables],
                                composedVariables= self.availableMessages,
                                md5Hash=self.md5Hash,
                                isOneToMany=isOneToMany,
                                compliance=self.compliance)
                    ret = v.Process()
                    if ret != None:
                        return ret
                    self.variables = v.get()
                    rBracePosition = j

                self.isEnum = isEnum
            
            if rBracePosition is not None:
                if token[0] == "PCOMMA":
                    self.visibility = "PRIVATE"
                if token[0] == 'ID':
                    
                    self.tableName = tokens[j][1]

        if self.name is None:
            
            return Error(errCl=Classes.MESSAGES, 
                        errTp=Types.NO_NAME_IN_MESSAGE, 
                        FileName=self.file,
                        FileLine='1',
                        CharacterNumber='1')

        return None

    def __str__(self) -> str:
        st = "access_modifiers:{} name:{} variables:[".format(self.access_modifiers,self.name)
        for v in self.variables:
            st += "{}, ".format(v.__str__())
        st+="] tableName:{} visibility:{}".format(self.tableName,self.visibility)
        if self.event_cache_mode is not None:
            st += " event_cache_mode:{}".format(self.event_cache_mode)
        st += " \n"
        return st



