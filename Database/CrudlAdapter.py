"""Stage 8 (database) -- CRUDL code generation.

For each message that declares a table, emit a header-only data-access object
(<name>_<hash>_crudl.h) over the vendored SQLite providing create/read/update/
remove/list plus create_table/drop_table. Columns come from the shared
Database.model so the SQL matches the generated schema.

Scalar/enum fields, singular FKs to table-bearing messages, the flattened
scalar/enum sub-fields of a non-table composed field, map<K,V> fields, and
repeated scalar fields (the last two each persisted in a child table keyed by the
parent's primary key) are handled. The runtime needs sqlite3 on the include/link
path (vendored under third_party/sqlite).
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate
from Database.model import (analyze, create_table_sql, type_registry,
                            map_fields, repeated_fields)

CRUDL_EXT = "_crudl.h"

_CRUDL = loadTemplate(__file__, "crudl.h.tmpl")


def _bind_line(col, index, src):
    acc = col.getter(src)
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
        val = "p ? reinterpret_cast<const char*>(p) : \"\""
        return ("        {{ const unsigned char* p = ::sqlite3_column_text(st, {i});"
                " {set}; }}".format(i=index, set=col.set_stmt(val)))
    if col.kind == "enum":
        val = "static_cast<::{et}>(::sqlite3_column_int(st, {i}))".format(
            et=col.enum_type, i=index)
        return "        {};".format(col.set_stmt(val))
    fn = {"int": "sqlite3_column_int", "int64": "sqlite3_column_int64",
          "double": "sqlite3_column_double"}[col.kind]
    val = "::{fn}(st, {i})".format(fn=fn, i=index)
    return "        {};".format(col.set_stmt(val))


# -- scalar bind/read snippets for map child tables (stmt var passed in) -------
def _bind_scalar(stmt, kind, index, expr):
    if kind == "text":
        return ("::sqlite3_bind_text({s}, {i}, {e}.c_str(), -1, SQLITE_TRANSIENT);"
                .format(s=stmt, i=index, e=expr))
    fn = {"int": "sqlite3_bind_int", "int64": "sqlite3_bind_int64",
          "double": "sqlite3_bind_double"}[kind]
    return "::{fn}({s}, {i}, {e});".format(fn=fn, s=stmt, i=index, e=expr)


def _col_decl(kind, index, var):
    """Declare local ``var`` reading column ``index`` from stmt ``cs``."""
    if kind == "text":
        return ("const unsigned char* {v}p = ::sqlite3_column_text(cs, {i}); "
                "const std::string {v} = {v}p ? reinterpret_cast<const char*>({v}p)"
                " : \"\";".format(v=var, i=index))
    ctype = {"int": "int", "int64": "long long", "double": "double"}[kind]
    fn = {"int": "sqlite3_column_int", "int64": "sqlite3_column_int64",
          "double": "sqlite3_column_double"}[kind]
    return "const {c} {v} = ::{fn}(cs, {i});".format(c=ctype, v=var, fn=fn, i=index)


class CrudlAdapter:
    def __init__(self, messages, dest) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "db")
        self.types = type_registry(messages)
        self.byName = {m.name: m for m in messages}
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
        # scalar/enum columns and flattened-embed columns bind the same way (the
        # embed columns just read/write through the parent field); only FK
        # columns (child primary key) need the create/load hooks.
        scalar = [c for c in columns if c.bindable or c.embed]
        fk_cols = [c for c in columns if c.fk_table]
        id_col = next((c for c in scalar if c.pk), None)
        non_id = [c for c in scalar if not c.pk]

        # INSERT/SELECT columns: scalar/enum/embed first, then FK columns.
        insert_all = scalar + fk_cols
        update_all = non_id + fk_cols

        create_bind = "\n".join(
            [_bind_line(c, i, "msg") for i, c in enumerate(scalar, start=1)] +
            [self._fk_bind(c, i)
             for i, c in enumerate(fk_cols, start=len(scalar) + 1)])
        update_bind = "\n".join(
            [_bind_line(c, i, "msg") for i, c in enumerate(non_id, start=1)] +
            [self._fk_bind(c, i)
             for i, c in enumerate(fk_cols, start=len(non_id) + 1)])
        extract = "\n".join(
            [_extract_line(c, i) for i, c in enumerate(scalar)] +
            [self._fk_extract(c, i)
             for i, c in enumerate(fk_cols, start=len(scalar))])

        maps = map_fields(msg, self.types)
        reps = repeated_fields(msg, self.types)

        return _CRUDL.format(
            guard="HARPIA_CRUDL_{}_{}".format(msg.name.upper(), msg.md5Hash),
            pb_header="protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash),
            fk_includes=self._fk_includes(fk_cols, reps),
            fk_precreate=self._fk_hooks(fk_cols, "create"),
            fk_preupdate=self._fk_hooks(fk_cols, "update"),
            cls=msg.name,
            table=msg.tableName,
            create_table_sql=create_table_sql(msg, types=self.types).replace('"', '\\"'),
            insert_cols=", ".join('\\"{}\\"'.format(c.name) for c in insert_all),
            insert_qs=", ".join("?" * len(insert_all)),
            select_cols=", ".join('\\"{}\\"'.format(c.name) for c in insert_all),
            create_bind=create_bind,
            update_bind=update_bind,
            update_set=", ".join('\\"{}\\" = ?'.format(c.name) for c in update_all),
            id_bind_index=len(update_all) + 1,
            id_col=id_col.name if id_col else "rowid",
            id_accessor=id_col.accessor if id_col else "rowid",
            extract=extract,
            map_create_tables=(self._map_create_tables(maps, columns)
                               + self._rep_create_tables(reps, columns)),
            map_drop_tables=self._child_drop_tables(maps + reps),
            map_create=(self._map_write(maps, id_col, "create")
                        + self._rep_write(reps, id_col, "create")),
            map_update=(self._map_write(maps, id_col, "update")
                        + self._rep_write(reps, id_col, "update")),
            map_read=self._map_read(maps, id_col) + self._rep_read(reps, id_col),
            map_remove=self._child_remove(maps + reps),
        )

    # -- composed FK (message whose target owns a table) -------------------
    def _child_by_name(self, target):
        m = self.byName[target]
        cols, _ = analyze(m, self.types)
        pk = next((c for c in cols if c.bindable and c.pk), None)
        return {
            "dao": "::harpia::db::{}_dao".format(m.name),
            "header": "db/{}_{}_crudl.h".format(m.name, m.md5Hash),
            "pk": pk.accessor if pk else "rowid",
        }

    def _child(self, col):
        return self._child_by_name(col.fk_target)

    def _fk_bind(self, col, index):
        ch = self._child(col)
        return "        ::sqlite3_bind_int64(st, {i}, msg.{a}().{pk}());".format(
            i=index, a=col.accessor, pk=ch["pk"])

    def _fk_extract(self, col, index):
        ch = self._child(col)
        return ("        {{ const long long _fk{i} = "
                "::sqlite3_column_int64(st, {i}); if (_fk{i}) {{ {dao} _c(db_); "
                "_c.read(_fk{i}, msg->mutable_{a}()); }} }}".format(
                    i=index, dao=ch["dao"], a=col.accessor))

    def _fk_hooks(self, fk_cols, op):
        if not fk_cols:
            return ""
        lines = []
        for c in fk_cols:
            dao = self._child(c)["dao"]
            if op == "create":
                lines.append(
                    "        if (msg.has_{a}()) {{ {dao} _c(db_); "
                    "if (!_c.create(msg.{a}())) return false; }}".format(
                        a=c.accessor, dao=dao))
            else:
                lines.append(
                    "        if (msg.has_{a}()) {{ {dao} _c(db_); "
                    "_c.update(msg.{a}()); }}".format(a=c.accessor, dao=dao))
        return "\n".join(lines) + "\n"

    def _fk_includes(self, fk_cols, reps=()):
        # child-DAO headers for both singular FK columns and repeated FK fields
        seen = []
        for c in fk_cols:
            h = self._child(c)["header"]
            if h not in seen:
                seen.append(h)
        for rf in reps:
            if not rf.fk_target:
                continue
            h = self._child_by_name(rf.fk_target)["header"]
            if h not in seen:
                seen.append(h)
        if not seen:
            return ""
        return "\n" + "\n".join('#include "{}"'.format(h) for h in seen)

    # -- map<K,V> child tables (keyed by the parent's primary key) ----------
    def _map_create_tables(self, maps, columns):
        if not maps:
            return ""
        pk = next((c for c in columns if c.pk), None)
        owner_sql = pk.sql_type if pk else "INTEGER"
        parts = []
        for mf in maps:
            sql = ('CREATE TABLE IF NOT EXISTS \\"{child}\\" (\\"owner\\" {o}, '
                   '\\"key\\" {k}, \\"value\\" {v}, '
                   'PRIMARY KEY(\\"owner\\", \\"key\\"));').format(
                       child=mf.child_table, o=owner_sql, k=mf.key_sql, v=mf.val_sql)
            parts.append(' && exec("{}")'.format(sql))
        return "".join(parts)

    def _child_drop_tables(self, children):
        # drop child tables (maps + repeated) before the parent table
        return "".join(
            'exec("DROP TABLE IF EXISTS \\"{}\\";") && '.format(ch.child_table)
            for ch in children)

    def _map_write(self, maps, id_col, op):
        """create/update body: (clear then) re-insert each map's entries."""
        if not maps:
            return ""
        owner_kind = id_col.kind if id_col else "int64"
        owner = "msg.{}()".format(id_col.accessor) if id_col else "0"
        blocks = []
        for mf in maps:
            L = []
            if op == "update":
                L += [
                    "        {",
                    "            ::sqlite3_stmt* ds = nullptr;",
                    '            if (::sqlite3_prepare_v2(db_, "DELETE FROM \\"'
                    + mf.child_table + '\\" WHERE \\"owner\\" = ?;", -1, &ds, '
                    "nullptr) == SQLITE_OK) {",
                    "                " + _bind_scalar("ds", owner_kind, 1, owner),
                    "                ::sqlite3_step(ds);",
                    "                ::sqlite3_finalize(ds);",
                    "            }",
                    "        }",
                ]
            L += [
                "        for (const auto& kv : " + mf.entries("msg") + ") {",
                "            ::sqlite3_stmt* cs = nullptr;",
                '            if (::sqlite3_prepare_v2(db_, "INSERT INTO \\"'
                + mf.child_table + '\\" (\\"owner\\", \\"key\\", \\"value\\") '
                'VALUES (?, ?, ?);", -1, &cs, nullptr) != SQLITE_OK) return false;',
                "            " + _bind_scalar("cs", owner_kind, 1, owner),
                "            " + _bind_scalar("cs", mf.key_kind, 2, "kv.first"),
                "            " + _bind_scalar("cs", mf.val_kind, 3, "kv.second"),
                "            const bool mok = ::sqlite3_step(cs) == SQLITE_DONE;",
                "            ::sqlite3_finalize(cs);",
                "            if (!mok) return false;",
                "        }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"

    def _map_read(self, maps, id_col):
        if not maps:
            return ""
        owner_kind = id_col.kind if id_col else "int64"
        owner = "msg->{}()".format(id_col.accessor) if id_col else "0"
        blocks = []
        for mf in maps:
            L = [
                "        {",
                "            ::sqlite3_stmt* cs = nullptr;",
                '            if (::sqlite3_prepare_v2(db_, "SELECT \\"key\\", '
                '\\"value\\" FROM \\"' + mf.child_table + '\\" WHERE \\"owner\\" '
                '= ?;", -1, &cs, nullptr) == SQLITE_OK) {',
                "                " + _bind_scalar("cs", owner_kind, 1, owner),
                "                while (::sqlite3_step(cs) == SQLITE_ROW) {",
                "                    " + _col_decl(mf.key_kind, 0, "_k"),
                "                    " + _col_decl(mf.val_kind, 1, "_v"),
                "                    (*" + mf.mutable() + ")[_k] = _v;",
                "                }",
                "                ::sqlite3_finalize(cs);",
                "            }",
                "        }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"

    def _child_remove(self, children):
        if not children:
            return ""
        blocks = []
        for ch in children:
            L = [
                "        {",
                "            ::sqlite3_stmt* ds = nullptr;",
                '            if (::sqlite3_prepare_v2(db_, "DELETE FROM \\"'
                + ch.child_table + '\\" WHERE \\"owner\\" = ?;", -1, &ds, '
                "nullptr) == SQLITE_OK) {",
                "                ::sqlite3_bind_int64(ds, 1, id);",
                "                ::sqlite3_step(ds);",
                "                ::sqlite3_finalize(ds);",
                "            }",
                "        }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"

    # -- repeated scalar child tables (owner, ordinal, value) ---------------
    def _rep_create_tables(self, reps, columns):
        if not reps:
            return ""
        pk = next((c for c in columns if c.pk), None)
        owner_sql = pk.sql_type if pk else "INTEGER"
        parts = []
        for rf in reps:
            sql = ('CREATE TABLE IF NOT EXISTS \\"{child}\\" (\\"owner\\" {o}, '
                   '\\"ordinal\\" INTEGER, \\"value\\" {v}, '
                   'PRIMARY KEY(\\"owner\\", \\"ordinal\\"));').format(
                       child=rf.child_table, o=owner_sql, v=rf.val_sql)
            parts.append(' && exec("{}")'.format(sql))
        return "".join(parts)

    def _rep_write(self, reps, id_col, op):
        """create/update body: (clear then) re-insert each repeated field's values
        with a running ordinal that preserves order."""
        if not reps:
            return ""
        owner_kind = id_col.kind if id_col else "int64"
        owner = "msg.{}()".format(id_col.accessor) if id_col else "0"
        blocks = []
        for rf in reps:
            L = []
            if op == "update":
                L += [
                    "        {",
                    "            ::sqlite3_stmt* ds = nullptr;",
                    '            if (::sqlite3_prepare_v2(db_, "DELETE FROM \\"'
                    + rf.child_table + '\\" WHERE \\"owner\\" = ?;", -1, &ds, '
                    "nullptr) == SQLITE_OK) {",
                    "                " + _bind_scalar("ds", owner_kind, 1, owner),
                    "                ::sqlite3_step(ds);",
                    "                ::sqlite3_finalize(ds);",
                    "            }",
                    "        }",
                ]
            L += [
                "        {",
                "            long long _ord = 0;",
                "            for (const auto& rv : " + rf.entries("msg") + ") {",
            ]
            if rf.fk_target:
                # 1-to-many: persist the child via its DAO, link its primary key
                ch = self._child_by_name(rf.fk_target)
                child_op = ("if (!_c.create(rv)) return false;" if op == "create"
                            else "_c.update(rv);")
                L += [
                    "                " + ch["dao"] + " _c(db_);",
                    "                " + child_op,
                ]
            L += [
                "                ::sqlite3_stmt* cs = nullptr;",
                '                if (::sqlite3_prepare_v2(db_, "INSERT INTO \\"'
                + rf.child_table + '\\" (\\"owner\\", \\"ordinal\\", \\"value\\") '
                'VALUES (?, ?, ?);", -1, &cs, nullptr) != SQLITE_OK) return false;',
                "                " + _bind_scalar("cs", owner_kind, 1, owner),
                "                ::sqlite3_bind_int64(cs, 2, _ord++);",
            ]
            if rf.fk_target:
                ch = self._child_by_name(rf.fk_target)
                L.append("                ::sqlite3_bind_int64(cs, 3, rv.{}());"
                         .format(ch["pk"]))
            else:
                L.append("                " + _bind_scalar("cs", rf.val_kind, 3, "rv"))
            L += [
                "                const bool mok = ::sqlite3_step(cs) == SQLITE_DONE;",
                "                ::sqlite3_finalize(cs);",
                "                if (!mok) return false;",
                "            }",
                "        }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"

    def _rep_read(self, reps, id_col):
        if not reps:
            return ""
        owner_kind = id_col.kind if id_col else "int64"
        owner = "msg->{}()".format(id_col.accessor) if id_col else "0"
        blocks = []
        for rf in reps:
            L = [
                "        {",
                "            ::sqlite3_stmt* cs = nullptr;",
                '            if (::sqlite3_prepare_v2(db_, "SELECT \\"value\\" '
                'FROM \\"' + rf.child_table + '\\" WHERE \\"owner\\" = ? '
                'ORDER BY \\"ordinal\\";", -1, &cs, nullptr) == SQLITE_OK) {',
                "                " + _bind_scalar("cs", owner_kind, 1, owner),
                "                while (::sqlite3_step(cs) == SQLITE_ROW) {",
            ]
            if rf.fk_target:
                # load each child by its primary key via the child DAO
                ch = self._child_by_name(rf.fk_target)
                L += [
                    "                    const long long _fk = ::sqlite3_column_int64(cs, 0);",
                    "                    " + ch["dao"] + " _c(db_);",
                    "                    _c.read(_fk, msg->add_" + rf.field + "());",
                ]
            else:
                L += [
                    "                    " + _col_decl(rf.val_kind, 0, "_v"),
                    "                    " + rf.add_stmt("_v") + ";",
                ]
            L += [
                "                }",
                "                ::sqlite3_finalize(cs);",
                "            }",
                "        }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"
