"""Stage 9 -- JSON adapter generation.

For every (non-enum) message, emit a small header-only C++ adapter that wraps
protobuf's own JSON support (google::protobuf::util) so callers can move a
message to/from JSON without touching the protobuf API directly:

  - to_json(msg, *out)      message  -> JSON          (spec 9 / 8.1)
  - from_json(in, *msg)     JSON     -> message        (spec 9 / 8.2)
  - is_valid_json(in)       JSON validity vs schema    (spec 9 / 8.1 checker)

The adapters live next to the protoc output, under
<dest>/generated/cpp/json/<name>_<hash>_json.h, and include the matching
generated message header via the protoc include root (-I <dest>/generated/cpp).

Generation is pure text emission and does not require protoc to have run; the
adapters only *compile* once Stage 7 has produced the .pb.h headers (done inside
the harpia Docker image).

The database-backed JSON functions in the spec (export/import to/from the
database, 8.3-8.6) are intentionally deferred: they depend on Stage 8 (database
access), which is not implemented yet.
"""
import os

from Logger.logger import logger
from Errors.Error import Error, Types, Classes
from Util.util import loadTemplate

JSON_EXT = "_json.h"

# C++ adapter template (Python str.format placeholders); see templates/.
_TEMPLATE = loadTemplate(__file__, "adapter.h.tmpl")


class JsonAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "json")
        self.log = logger(outFile=None, moduleName="JsonAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False):
                # enums are carried inside messages; no standalone adapter
                continue
            header = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, JSON_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(header)
            written += 1

        if written == 0:
            self.log.print("no messages to generate JSON adapters for")
            return Error(errCl=Classes.MESSAGES,
                         errTp=Types.NOTHING_TO_REPORT,
                         FileName=self.outDir)

        self.log.print("generated {} JSON adapter(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        pbHeader = "protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash)
        cls = "::{}".format(msg.name)
        guard = "HARPIA_JSON_{}_{}".format(msg.name.upper(), msg.md5Hash)
        return _TEMPLATE.format(guard=guard, pb_header=pbHeader, cls=cls,
                                name=msg.name)
