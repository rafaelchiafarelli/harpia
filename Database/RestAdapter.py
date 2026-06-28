"""Stage 12 -- RESTful HTTP bindings.

For each table-bearing message, emit a header (<name>_<hash>_rest.h) that
registers CRUD routes on a cpp-httplib server, backed by the CRUDL DAO with JSON
bodies (spec stage 12 / 11.1, REST for JSON):

  GET  <base>/<name>      list      GET    <base>/<name>/:id   read
  POST <base>/<name>      create    PUT    <base>/<name>/:id   update
                                    DELETE <base>/<name>/:id   delete

XML content-negotiation and the SOAP/REST-for-XML variants are deferred.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate

REST_EXT = "_rest.h"

_REST = loadTemplate(__file__, "rest.h.tmpl")


class RestAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "rest")
        self.log = logger(outFile=None, moduleName="RestAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            header = _REST.format(
                guard="HARPIA_REST_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, REST_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(header)
            written += 1
        self.log.print("generated {} REST binding(s) into {}".format(
            written, self.outDir))
        return None
