
            if token[0] == 'STREAM' or token[0] == '' or token[0] == 'PULL' or token[0] == 'PUSH' or token[0] == 'EVENT' or token[0] == 'PUSHPULL' or token[0] == 'MESSAGE':
                lBracePosition = 0
                rBracePosition = 0
                for j,t in enumerate(local_tokens[i:]):
                    if t[0] == 'LBRACE':
                        lBracePosition = j
                        break

                if lBracePosition == 0:
                    return Error(errCl=Classes.BRACES, 
                                 errTp=Types.LEFT_BRACE_NOT_FOUND, 
                                 FileName=self.file,
                                 FileLine=token[2],
                                 CharacterNumber=token[3])

                for j,t in enumerate(local_tokens[i+lBracePosition:]):
                    if t[0] == 'RBRACE':
                        rBracePosition = j
                        break

                if rBracePosition == 0:
                    return Error(errCl=Classes.BRACES, 
                                 errTp=Types.RIGHT_BRACE_NOT_FOUND, 
                                 FileName=self.file,
                                 FileLine=token[2],
                                 CharacterNumber=token[3])
                
                if len(local_tokens) == rBracePosition:
                    """message ends here"""
                    ##SHOULD BE A BREAK HERE SOMEWHERE
                
                if len(local_tokens) == rBracePosition+1:
                    if local_tokens[rBracePosition+1][0] != 'ID' and local_tokens[rBracePosition+1][0] != 'PCOMMA' and local_tokens[rBracePosition][0] != 'NEWLINE':
                        return Error(errCl=Classes.BRACES, 
                                    errTp=Types.MESSAGE_NOT_TERMINATED, 
                                    FileName=self.file,
                                    FileLine=token[2],
                                    CharacterNumber=token[3])       
                    else:
                        """message ends here"""
                         ##SHOULD BE A BREAK HERE SOMEWHERE
                
                if local_tokens[rBracePosition+1][0] == 'NEWLINE':
                    """message ends here"""
                    ##SHOULD BE A BREAK HERE SOMEWHERE
                else:
                    
                    if local_tokens[rBracePosition+1][0] != 'ID' and local_tokens[rBracePosition+1][0] != 'PCOMMA':
                        return Error(errCl=Classes.BRACES, 
                                    errTp=Types.MESSAGE_NOT_TERMINATED, 
                                    FileName=self.file,
                                    FileLine=token[2],
                                    CharacterNumber=token[3])                                
                    else:
                        if len(local_tokens) <= rBracePosition+2:
                            if local_tokens[rBracePosition+1][0] != 'PCOMMA':
                                return Error(errCl=Classes.BRACES, 
                                    errTp=Types.MESSAGE_NOT_TERMINATED, 
                                    FileName=self.file,
                                    FileLine=token[2],
                                    CharacterNumber=token[3])      
                            else:
                                """message ends here"""
                                ##SHOULD BE A BREAK HERE SOMEWHER
                        else:
                            if local_tokens[rBracePosition+2][0] == 'PCOMMA' and local_tokens[rBracePosition+2][0] == 'NEWLINE':

                        elif local_tokens[rBracePosition+1][0] == '':: 
                            if local_tokens[rBracePosition+1][0] != 'PCOMMA' and local_tokens[rBracePosition+1][0] != 'NEWLINE':
                                return Error(errCl=Classes.BRACES, 
                                            errTp=Types.MESSAGE_NOT_TERMINATED, 
                                            FileName=self.file,
                                            FileLine=token[2],
                                            CharacterNumber=token[3])
                            
                            if len(local_tokens) <= rBracePosition+2:
                                pCommaPosition = rBracePosition+2

            

            elif token[0] == 'COMMENT_START':
                
                for j,t in enumerate(original_tokens[i:]):

                    if t[0] == 'COMMENT_END':
                        break
                print("original:{} to remove:{}".format(len(original_tokens),len(original_tokens[i:i+j+1])))
                del original_tokens[i:i+j+1]
            else:
                self.tokens+=token            
