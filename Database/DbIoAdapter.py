"""Stage 8 (database) -- bulk import/export bridging CRUDL and the adapters.

For each table-bearing message, emit a header (<name>_<hash>_dbio.h) that moves
the whole table to/from JSON and XML by composing the CRUDL DAO (list/create)
with the JSON and XML adapters:

  - export_json / import_json   (newline-delimited JSON; spec 9 / 8.5-8.6)
  - export_xml  / import_xml     (<name>_list wrapper; spec 10 / 9.5-9.6)

These are the database-backed serialization functions that were deferred until
the database layer (CRUDL) existed.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate

DBIO_EXT = "_dbio.h"

_DBIO = loadTemplate(__file__, "dbio.h.tmpl")


class DbIoAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "dbio")
        self.log = logger(outFile=None, moduleName="DbIoAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            header = _DBIO.format(
                guard="HARPIA_DBIO_{}_{}".format(msg.name.upper(), msg.md5Hash),
                name=msg.name,
                hash=msg.md5Hash,
            )
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, DBIO_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(header)
            written += 1
        self.log.print("generated {} DB import/export header(s) into {}".format(
            written, self.outDir))
        return None
