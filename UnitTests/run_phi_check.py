#!/usr/bin/env python3
"""Run the harpia front-end + FileCreator (Stages 0-6) on a single .harpia
file and report, as one JSON object on stdout:

    {"error": None, "fields": [{"message": ..., "field": ..., "is_phi": bool}, ...],
     "proto": "<concatenated .proto text for every message>"}

or, on a front-end failure:

    {"error": "PRELEX|LEX|MSG <ErrorType>", "fields": [], "proto": ""}

Used by test_phi_modifier.py (Foundation F2) to inspect the AST's
`variable.is_phi` flag and confirm the emitted .proto is unaffected by it.
Mirrors run_frontend.py's pattern (fresh subprocess per invocation, required
because LexicalAnalyzer accumulates tokens in class-level state) plus the
FileCreator step from run_pipeline.py.

    python3 UnitTests/run_phi_check.py <harpia_file> <dest_dir>
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)
# Stay in the repo root (unlike run_frontend.py, which chdirs into the
# fixture's folder) so FileCreator's `readFromTemplate("Service.proto", ...)`
# -- a repo-root-relative "./Assets/..." lookup -- still resolves. pre_lex
# accepts an absolute harpia_file path directly (isFileInFolders takes an
# already-resolving path as-is), so no chdir is needed here.
os.chdir(_REPO_ROOT)

from LexicalAnalizer.LexicalAnalyzer import LexicalAnalyzer
from LexicalAnalizer.pre_lex import pre_lex
from LexicalAnalizer.MessageCreator import MessageCreator
from ProtoFile.FileCreator import FileCreator


def run(harpia_file, dest):
    harpia_file = os.path.abspath(harpia_file)
    folder = os.path.dirname(harpia_file)

    root = pre_lex(folders=[folder], file=harpia_file, dest=dest, includeFolder=folder)
    pre = root.process()
    if pre is not None:
        return {"error": "PRELEX {}".format(pre.errType.name), "fields": [], "proto": ""}

    lex = LexicalAnalyzer()
    lex_err = lex.process(harpia_file)
    if lex_err is not None:
        return {"error": "LEX {}".format(lex_err.errType.name), "fields": [], "proto": ""}
    lex.CommentRemover()
    lex.ImportRemover()

    factory = MessageCreator(filename=harpia_file, tokens=lex.getTokens(),
                             md5Hash=root.getHash())
    msg_err = factory.CreateMessages(beginToken=0)
    if msg_err is not None:
        return {"error": "MSG {}".format(msg_err.errType.name), "fields": [], "proto": ""}

    fields = []
    protos = []
    imports = []
    for msg in factory.messages:
        for v in msg.variables:
            fields.append({"message": msg.name, "field": v.name,
                            "is_phi": bool(getattr(v, "is_phi", False))})
        fc = FileCreator(message=msg, imports=imports, dest=dest)
        fc.Process()
        protos.append(fc.messageData)

    return {"error": None, "fields": fields, "proto": "\n".join(protos)}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python3 UnitTests/run_phi_check.py <file> <dest>")
    # prefixed (like run_frontend.py's "RESULT ") so the caller can pick this
    # line out of the logger's other stdout noise.
    print("PHI_CHECK_RESULT " + json.dumps(run(sys.argv[1], sys.argv[2])))
