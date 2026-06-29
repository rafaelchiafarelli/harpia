"""Stage 8 (database) -- CRUDL code generation.

For each message that declares a table, emit a header-only data-access object
(<name>_<hash>_crudl.h) over the vendored SQLite providing create/read/update/
remove/list plus create_table/drop_table. Columns come from the shared
Database.model so the SQL matches the generated schema.

Only scalar fields are persisted; composed (FK) and repeated/map fields are not
bound yet (the table still has the FK columns, left NULL). The runtime needs
sqlite3 on the include/link path (vendored under third_party/sqlite).
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate
from Database.model import analyze, create_table_sql, type_registry

CRUDL_EXT = "_crudl.h"

_CRUDL = loadTemplate(__file__, "crudl.h.tmpl")


def _bind_line(col, index, src):
    acc = "{}.{}()".format(src, col.accessor)
    if col.kind == "text":
        return ("        ::sqlite3_bind_text(st, {i}, {acc}.c_str(), -1, "
                "SQLITE_TRANSIENT);".format(i=index, acc=acc))
    if col.kind == "enum":
        return ("        ::sqlite3_bind_int(st, {i}, static_cast<int>({acc}));"
                .format(i=index, acc=acc))
    fn = {"int": "sqlite3_bind_int", "int64": "sqlite3_bind_int64",
          "double": "sqlite3_bind_double"}[col.kind]
    return "        ::{fn}(st, {i}, {acc});".format(fn=fn, i=index, acc=acc)


def _extract_line(col, index):
    if col.kind == "text":
        return ("        {{ const unsigned char* p = ::sqlite3_column_text(st, {i});"
                " msg->set_{acc}(p ? reinterpret_cast<const char*>(p) : \"\"); }}"
                .format(i=index, acc=col.accessor))
    if col.kind == "enum":
        return ("        msg->set_{acc}(static_cast<::{et}>("
                "::sqlite3_column_int(st, {i})));".format(
                    acc=col.accessor, et=col.enum_type, i=index))
    fn = {"int": "sqlite3_column_int", "int64": "sqlite3_column_int64",
          "double": "sqlite3_column_double"}[col.kind]
    return "        msg->set_{acc}(::{fn}(st, {i}));".format(
        acc=col.accessor, fn=fn, i=index)


class CrudlAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "db")
        self.types = type_registry(messages)
        self.log = logger(outFile=None, moduleName="CrudlAdapter")

    def Process(self):
        os.makedirs(self.outDir, exist_ok=True)
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            header = self._render(msg)
            fileName = "{}_{}{}".format(msg.name, msg.md5Hash, CRUDL_EXT)
            with open(os.path.join(self.outDir, fileName), "w") as out:
                out.write(header)
            written += 1
        self.log.print("generated {} CRUDL DAO(s) into {}".format(
            written, self.outDir))
        return None

    def _render(self, msg):
        columns, _ = analyze(msg, self.types)
        bindable = [c for c in columns if c.bindable]
        id_col = next((c for c in bindable if c.pk), None)
        non_id = [c for c in bindable if not c.pk]

        create_bind = "\n".join(
            _bind_line(c, i, "msg") for i, c in enumerate(bindable, start=1))
        update_bind = "\n".join(
            _bind_line(c, i, "msg") for i, c in enumerate(non_id, start=1))
        extract = "\n".join(
            _extract_line(c, i) for i, c in enumerate(bindable))

        cols_csv = ", ".join('\\"{}\\"'.format(c.name) for c in bindable)
        return _CRUDL.format(
            guard="HARPIA_CRUDL_{}_{}".format(msg.name.upper(), msg.md5Hash),
            pb_header="protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash),
            cls=msg.name,
            table=msg.tableName,
            create_table_sql=create_table_sql(msg, types=self.types).replace('"', '\\"'),
            insert_cols=cols_csv,
            insert_qs=", ".join("?" * len(bindable)),
            select_cols=cols_csv,
            create_bind=create_bind,
            update_bind=update_bind,
            update_set=", ".join('\\"{}\\" = ?'.format(c.name) for c in non_id),
            id_bind_index=len(non_id) + 1,
            id_col=id_col.name if id_col else "rowid",
            id_accessor=id_col.accessor if id_col else "rowid",
            extract=extract,
        )
