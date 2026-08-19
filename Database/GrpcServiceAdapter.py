"""Stage 13 -- gRPC service implementation (wires the generated service to CRUDL).

GrpcCompiler emits the client stubs and abstract server skeletons from each
<name>_service.proto. This adapter closes the loop for every table-bearing
message: it emits a concrete service implementation
(<name>_<hash>_grpc.h) whose RPCs call the CRUDL DAO --

  push      -> dao.create      pullByID -> dao.read
  streamSrc -> dao.list        heartBeat -> echo

so the gRPC transport becomes a real end-to-end path over SQLite (like the ZMQ
transport already is). Header-only C++; compiles once Stage 7 + Stage 13
(GrpcCompiler) have produced the message and service code. Non-table messages get
no implementation (there is no DAO to back them). The data operations enforce the
generated access credential via x-user/x-pswd call metadata (UNAUTHENTICATED on
mismatch), mirroring SOAP/REST; heartBeat stays open.
"""
import os

from logger.logger import logger
from util.util import loadTemplate, write_if_different

GRPC_EXT = "_grpc.h"

_GRPC = loadTemplate(__file__, "grpc_service.h.tmpl")


class GrpcServiceAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "grpc")
        self.log = logger(outFile=None, moduleName="GrpcServiceAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            header = _GRPC.format(
                guard="HARPIA_GRPC_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, GRPC_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1
        self.log.print("generated {} gRPC service impl(s) into {}".format(
            written, self.outDir))
        return None
