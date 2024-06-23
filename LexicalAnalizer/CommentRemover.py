
## comment remover will remove all comments from the generated lexic
import copy

class CommentRemover():
    tokens = []
    def remover(self, tokens):
        original_tokens = []
        original_tokens = copy.deepcopy(tokens)
        for i,token in enumerate(original_tokens):
            if token[0] == 'COMMENT_LINE':
                for j,t in enumerate(original_tokens[i:]):
                    if t[0] == 'NEWLINE':
                        break
                del original_tokens[i:i+j]
            elif token[0] == 'COMMENT_START':
                for j,t in enumerate(original_tokens[i:]):
                    if t[0] == 'COMMENT_END':
                        break
                del original_tokens[i:i+j+1]
            else:
                self.tokens.append(token)
        return self.tokens
