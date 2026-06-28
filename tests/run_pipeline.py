#!/usr/bin/env python3
"""Standalone harness that runs the harpia front-end pipeline on
HarpiaTest/test.harpia and dumps its intermediate artifacts so they can be
snapshotted as golden files.

It mirrors the orchestration in main.py exactly, but in addition to writing the
normal build output it captures:

  - tokens.txt   : the token stream after comment/import removal
  - messages.txt : the Message objects produced by MessageCreator
  - proto/       : every generated .proto (message + service) files

Run from the repository root:

    python3 tests/run_pipeline.py <output_dir>

Each invocation is a fresh process, which matters: LexicalAnalyzer accumulates
tokens in a class-level list, so capturing must happen in a clean interpreter.
"""
import os
import shutil
import sys

# Run relative to the repository root regardless of how the script is invoked;
# the harpia packages are imported by their top-level names and the pipeline
# uses ./HarpiaTest and ./Assets relative paths.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from LexicalAnalizer.pre_lex import pre_lex
from LexicalAnalizer.MessageCreator import MessageCreator
from ProtoFile.FileCreator import FileCreator
from JsonAdapter.JsonAdapter import JsonAdapter
from ZmqAdapter.ZmqAdapter import ZmqAdapter
from Util.util import copyCMakeFiles, copyServerClientTemplates, copyBasicProtos


def run(output_dir):
    local_folder = os.getcwd()
    test_file = "./HarpiaTest/test.harpia"
    include_folder = "./HarpiaTest/Include"
    build_dir = os.path.join(output_dir, "build")

    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir, exist_ok=True)

    # 0. pre-process / include resolution
    root_file = pre_lex(folders=[local_folder], file=test_file,
                        dest=build_dir, includeFolder=include_folder)
    pre_result = root_file.process()
    if pre_result is not None:
        raise SystemExit("pre_lex error: {}".format(pre_result))

    list_of_includes = root_file.getListOfHarpias()

    # 1. lexical analysis of the main file
    main_lex = LexicalAnalyzer()
    if main_lex.process(test_file) is not None:
        raise SystemExit("lexical error in main file")
    main_lex.CommentRemover()
    main_lex.ImportRemover()

    # 2. lexical analysis of each include
    analizer = main_lex
    for inc in list_of_includes:
        inc_pre = pre_lex(folders=[local_folder], file=inc,
                          dest=build_dir, includeFolder=include_folder)
        if inc_pre.process() is not None:
            raise SystemExit("pre_lex error in include {}".format(inc))
        analizer = LexicalAnalyzer()
        if analizer.process(inc) is not None:
            raise SystemExit("lexical error in include {}".format(inc))
        analizer.CommentRemover()
        analizer.ImportRemover()

    # getTokens() returns the class-level accumulated stream (main + includes),
    # exactly as main.py relies on.
    tokens = analizer.getTokens()

    # 3. message construction
    msg_factory = MessageCreator(filename=test_file, tokens=tokens,
                                 md5Hash=root_file.getHash())
    msg_error = msg_factory.CreateMessages(beginToken=0)
    if msg_error is not None:
        raise SystemExit("message creation error: {}".format(msg_error))

    # 4. proto / sidecar file emission
    imports = []
    for msg in msg_factory.messages:
        fc = FileCreator(message=msg, imports=imports, dest=build_dir)
        fc.Process()
        fc.save()
    copyBasicProtos(src="./Assets/proto/protofiles", dest=build_dir)
    copyServerClientTemplates(src="./Assets", dest=build_dir)
    copyCMakeFiles(src="./Assets", dest=build_dir)

    # 9. JSON adapters (header-only C++ over the protobuf messages)
    JsonAdapter(messages=msg_factory.messages, dest=build_dir).Process()

    # 13 (zmq). ZMQ/socket transport for push/pull + event/stream messages
    ZmqAdapter(messages=msg_factory.messages, dest=build_dir).Process()

    # --- capture artifacts -------------------------------------------------
    _dump_tokens(os.path.join(output_dir, "tokens.txt"), tokens)
    _dump_messages(os.path.join(output_dir, "messages.txt"), msg_factory.messages)
    _collect_protos(build_dir, os.path.join(output_dir, "proto"))
    _collect_json(build_dir, os.path.join(output_dir, "json"))
    _collect_zmq(build_dir, os.path.join(output_dir, "zmq"))


def _dump_tokens(path, tokens):
    with open(path, "w") as f:
        for t in tokens:
            # (type, lexeme, line, col)
            f.write("{}\n".format(t))


def _dump_messages(path, messages):
    with open(path, "w") as f:
        for msg in messages:
            f.write(msg.__str__())
            f.write("\n")


def _collect_protos(build_dir, dest):
    src = os.path.join(build_dir, "proto", "protofiles")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    for name in sorted(os.listdir(src)):
        if name.endswith(".proto"):
            shutil.copy2(os.path.join(src, name), os.path.join(dest, name))


def _collect_json(build_dir, dest):
    src = os.path.join(build_dir, "generated", "cpp", "json")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    if not os.path.isdir(src):
        return
    for name in sorted(os.listdir(src)):
        if name.endswith(".h"):
            shutil.copy2(os.path.join(src, name), os.path.join(dest, name))


def _collect_zmq(build_dir, dest):
    src = os.path.join(build_dir, "generated", "cpp", "zmq")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    if not os.path.isdir(src):
        return
    for name in sorted(os.listdir(src)):
        if name.endswith(".h"):
            shutil.copy2(os.path.join(src, name), os.path.join(dest, name))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python3 tests/run_pipeline.py <output_dir>")
    run(sys.argv[1])
