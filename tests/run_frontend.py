#!/usr/bin/env python3
"""Run the harpia front-end on a single .harpia file and report the outcome.

Prints one line:
    PRELEX <ErrorType>   pre_lex rejected the file
    LEX <ErrorType>      the lexer rejected it
    MSG <ErrorType>      message construction rejected it
    OK                   the file passed the whole front-end

Used by test_frontend.py to assert error paths. Each invocation is a fresh
process because LexicalAnalyzer accumulates tokens in class-level state.

    python3 tests/run_frontend.py <harpia_file> <dest_dir>
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from LexicalAnalizer.pre_lex import pre_lex
from LexicalAnalizer.MessageCreator import MessageCreator


def run(harpia_file, dest):
    # pre_lex/isFileInFolders resolve the file by joining folder + file, so it
    # must be a path relative to one of the folders. Mirror main.py: run from the
    # file's directory and refer to it by name.
    folder = os.path.dirname(os.path.abspath(harpia_file))
    harpia_file = os.path.basename(harpia_file)
    os.chdir(folder)

    root = pre_lex(folders=[folder], file=harpia_file, dest=dest,
                   includeFolder=folder)
    pre = root.process()
    if pre is not None:
        return "PRELEX {}".format(pre.errType.name)

    lex = LexicalAnalyzer()
    lex_err = lex.process(harpia_file)
    if lex_err is not None:
        return "LEX {}".format(lex_err.errType.name)
    lex.CommentRemover()
    lex.ImportRemover()

    factory = MessageCreator(filename=harpia_file, tokens=lex.getTokens(),
                             md5Hash=root.getHash())
    msg_err = factory.CreateMessages(beginToken=0)
    if msg_err is not None:
        return "MSG {}".format(msg_err.errType.name)
    return "OK"


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python3 tests/run_frontend.py <file> <dest>")
    # prefix so the caller can pick the result out of the logger's stdout noise
    print("RESULT " + run(sys.argv[1], sys.argv[2]))
