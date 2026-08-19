"""Stage 12 -- RESTful HTTP bindings.

For each table-bearing message, emit a header (<name>_<hash>_rest.h) that
registers CRUD routes on a Crow server (crow::SimpleApp), backed by the CRUDL
DAO (spec stage 12 / 11.1):

  GET  <base>/<name>      list      GET    <base>/<name>/:id   read
  POST <base>/<name>      create    PUT    <base>/<name>/:id   update
                                    DELETE <base>/<name>/:id   delete

GET list is paginated (?limit=&offset=) when the request supplies a limit or
the message declares a "pagination[size]" field (that size becomes the
default limit); with no limit in play it returns everything, unchanged from
before pagination support existed.

Content negotiation (spec stage 12): a request body is parsed as XML when its
Content-Type contains "xml" (else JSON), and a response is serialized as XML when
the Accept header asks for "xml" (else JSON), reusing the JSON and XML adapters.

Every route enforces the generated access credential (Stage 5 access rights): the
request must carry X-User: <name> and X-Pswd: <hash> headers, or it is rejected
with HTTP 401 (mirrors the SOAP endpoint, which gates on <credentials>).
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate, write_if_different
from Database.model import pagination_default

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
            default_limit = pagination_default(msg) or 0
            header = _REST.format(
                guard="HARPIA_REST_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
                default_limit=default_limit,
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, REST_EXT)
            write_if_different(os.path.join(self.outDir, fileName), header)
            written += 1
        self.log.print("generated {} REST binding(s) into {}".format(
            written, self.outDir))
        return None
