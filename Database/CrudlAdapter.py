"""Stage 8 (database) -- CRUDL code generation (SOCI-based).

For each message that declares a table, emit a header-only data-access object
(<name>_<hash>_crudl.h) providing create/read/update/remove/list plus
create_table/drop_table. The DAO is emitted against **SOCI** (soci::session,
use()/into(), :name placeholders), so one generated codebase runs on any SOCI
backend (SQLite today, PostgreSQL next). Columns come from the shared
Database.model so the SQL matches the generated schema.

Scalar/enum fields, singular FKs to table-bearing messages, the flattened
scalar/enum sub-fields of a non-table composed field, map<K,V> fields, and
repeated scalar/composed fields (child tables keyed by the parent's primary key)
are handled.

SOCI specifics baked into the generated code (see the DAO's header comment):
- every method returns bool via try/catch (SOCI throws on error);
- use()/into() bind by reference, so bound values are copied into named locals;
- all use() in a statement are POSITIONAL (mixing positional+named throws);
- into() is indicator-guarded so a NULL fetch does not throw.
"""
import os

from Logger.logger import logger
from Util.util import loadTemplate
from Database.backends import get_backend
from Database.model import (analyze, create_table_sql, type_registry,
                            map_fields, repeated_fields, RepeatedComposedField)

CRUDL_EXT = "_crudl.h"

_CRUDL = loadTemplate(__file__, "crudl.h.tmpl")

# neutral bind/read kind -> C++ local type
_CTYPE = {"text": "std::string", "int": "int", "int64": "long long",
          "double": "double", "enum": "int"}


def _local_ctype(kind):
    return _CTYPE[kind]


def _use_list(count, base, indent):
    """`, use(<base>0), use(<base>1), ...` wrapped onto a continuation line."""
    if count == 0:
        return ""
    uses = ", ".join("::soci::use({}{})".format(base, i) for i in range(count))
    return ",\n{}{}".format(indent, uses)


class CrudlAdapter:
    def __init__(self, messages, dest, backend=None) -> None:
        self.messages = messages
        self.dest = dest
        self.outDir = os.path.join(dest, "generated", "cpp", "db")
        self.types = type_registry(messages)
        self.byName = {m.name: m for m in messages}
        self.backend = backend or get_backend()
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
        columns, _ = analyze(msg, self.types, self.backend)
        scalar = [c for c in columns if c.bindable or c.embed]
        fk_cols = [c for c in columns if c.fk_table]
        id_col = next((c for c in scalar if c.pk), None)
        non_id = [c for c in scalar if not c.pk]

        # column order for INSERT/SELECT: scalar/enum/embed first, then FK.
        insert_all = scalar + fk_cols
        update_all = non_id + fk_cols

        maps = map_fields(msg, self.types, self.backend)
        reps = repeated_fields(msg, self.types, self.backend)

        return _CRUDL.format(
            guard="HARPIA_CRUDL_{}_{}".format(msg.name.upper(), msg.md5Hash),
            pb_header="protofiles/{}_{}.pb.h".format(msg.name, msg.md5Hash),
            fk_includes=self._fk_includes(fk_cols, reps),
            fk_precreate=self._fk_hooks(fk_cols, "create"),
            fk_preupdate=self._fk_hooks(fk_cols, "update"),
            cls=msg.name,
            table=msg.tableName,
            create_table_sql=create_table_sql(
                msg, types=self.types, backend=self.backend).replace('"', '\\"'),
            insert_cols=", ".join('\\"{}\\"'.format(c.name) for c in insert_all),
            insert_ph=", ".join(":c{}".format(i) for i in range(len(insert_all))),
            select_cols=", ".join('\\"{}\\"'.format(c.name) for c in insert_all),
            id_col=id_col.name if id_col else "rowid",
            create_locals=self._create_locals(scalar, fk_cols),
            create_use=_use_list(len(insert_all), "c", " " * 16),
            update_locals=self._update_locals(non_id, fk_cols, id_col),
            update_set=", ".join('\\"{}\\" = :c{}'.format(c.name, i)
                                 for i, c in enumerate(update_all)),
            update_use=self._update_use(len(update_all)),
            extract_locals=self._extract_locals(scalar, fk_cols),
            extract_into=self._extract_into(len(insert_all)),
            extract_set=self._extract_set(scalar),
            fk_extract=self._fk_extract(scalar, fk_cols),
            map_create_tables=(self._child_create_tables(maps, columns)
                               + self._child_create_tables(reps, columns,
                                                           repeated=True)),
            map_drop_tables=self._child_drop_tables(maps + reps),
            map_create=(self._map_write(maps, id_col, "create")
                        + self._rep_write(reps, id_col, "create")),
            map_update=(self._map_write(maps, id_col, "update")
                        + self._rep_write(reps, id_col, "update")),
            map_read=self._map_read(maps, id_col) + self._rep_read(reps, id_col),
            map_remove=self._child_remove(maps + reps),
        )

    # -- INSERT locals / SELECT locals -------------------------------------
    def _create_locals(self, scalar, fk_cols):
        lines = []
        i = 0
        for c in scalar:
            lines.append("            " + self._value_local("c", i, c))
            i += 1
        for c in fk_cols:
            ch = self._child(c)
            lines.append("            long long c{i} = msg.{a}().{pk}();".format(
                i=i, a=c.accessor, pk=ch["pk"]))
            i += 1
        return "".join(l + "\n" for l in lines)

    def _value_local(self, base, i, col, src="msg"):
        """A named local holding column ``col``'s value read from ``src`` (for
        use). ``src`` defaults to "msg"; a repeated-composed field's write
        loop passes its per-element loop variable instead."""
        if col.kind == "enum":
            return "int {b}{i} = static_cast<int>({g});".format(
                b=base, i=i, g=col.getter(src))
        return "{t} {b}{i} = {g};".format(
            t=_local_ctype(col.kind), b=base, i=i, g=col.getter(src))

    def _update_locals(self, non_id, fk_cols, id_col):
        lines = []
        i = 0
        for c in non_id:
            lines.append("            " + self._value_local("c", i, c))
            i += 1
        for c in fk_cols:
            ch = self._child(c)
            lines.append("            long long c{i} = msg.{a}().{pk}();".format(
                i=i, a=c.accessor, pk=ch["pk"]))
            i += 1
        acc = id_col.accessor if id_col else "rowid"
        lines.append("            long long cid = msg.{}();".format(acc))
        return "".join(l + "\n" for l in lines)

    def _update_use(self, n_update):
        uses = ["::soci::use(c{})".format(i) for i in range(n_update)]
        uses.append("::soci::use(cid)")
        return ",\n{}{}".format(" " * 16, ", ".join(uses))

    def _extract_locals(self, scalar, fk_cols):
        lines = []
        i = 0
        for c in scalar:
            lines.append("            " + self._read_local(i, c.kind))
            i += 1
        for _ in fk_cols:
            lines.append("            " + self._read_local(i, "int64"))
            i += 1
        return "".join(l + "\n" for l in lines)

    def _read_local(self, i, kind):
        if kind == "text":
            return "std::string l{i}; ::soci::indicator n{i};".format(i=i)
        ctype = _local_ctype("int" if kind == "enum" else kind)
        return "{t} l{i} = 0; ::soci::indicator n{i};".format(t=ctype, i=i)

    def _extract_into(self, count):
        intos = ", ".join("::soci::into(l{i}, n{i})".format(i=i)
                          for i in range(count))
        return ",\n{}{}".format(" " * 16, intos)

    def _extract_set(self, scalar):
        # scalar/enum/embed columns are set directly from the into-locals
        # (indicator-guarded); FK columns are handled by _fk_extract.
        lines = []
        for i, c in enumerate(scalar):
            if c.kind == "text":
                val = "n{i} == ::soci::i_ok ? l{i} : std::string()".format(i=i)
            elif c.kind == "enum":
                val = ("static_cast<::{et}>(n{i} == ::soci::i_ok ? l{i} : 0)"
                       .format(et=c.enum_type, i=i))
            else:
                val = "n{i} == ::soci::i_ok ? l{i} : 0".format(i=i)
            lines.append("                {};".format(c.set_stmt(val)))
        return "".join(l + "\n" for l in lines)

    # -- composed FK (message whose target owns a table) -------------------
    def _child_by_name(self, target):
        m = self.byName[target]
        cols, _ = analyze(m, self.types, self.backend)
        pk = next((c for c in cols if c.bindable and c.pk), None)
        return {
            "dao": "::harpia::db::{}_dao".format(m.name),
            "header": "db/{}_{}_crudl.h".format(m.name, m.md5Hash),
            "pk": pk.accessor if pk else "rowid",
        }

    def _child(self, col):
        return self._child_by_name(col.fk_target)

    def _fk_extract(self, scalar, fk_cols):
        # FK locals follow the scalar ones in SELECT order; each holds the child's
        # primary key -- load the child via its own DAO when present.
        lines = []
        for j, c in enumerate(fk_cols):
            i = len(scalar) + j
            ch = self._child(c)
            lines.append(
                "                if (n{i} == ::soci::i_ok && l{i}) {{ {dao} _c(db_); "
                "_c.read(l{i}, msg->mutable_{a}()); }}".format(
                    i=i, dao=ch["dao"], a=c.accessor))
        return "".join(l + "\n" for l in lines)

    def _fk_hooks(self, fk_cols, op):
        if not fk_cols:
            return ""
        lines = []
        for c in fk_cols:
            dao = self._child(c)["dao"]
            if op == "create":
                lines.append(
                    "            if (msg.has_{a}()) {{ {dao} _c(db_); "
                    "if (!_c.create(msg.{a}())) return false; }}".format(
                        a=c.accessor, dao=dao))
            else:
                lines.append(
                    "            if (msg.has_{a}()) {{ {dao} _c(db_); "
                    "_c.update(msg.{a}()); }}".format(a=c.accessor, dao=dao))
        return "\n".join(lines) + "\n"

    def _fk_includes(self, fk_cols, reps=()):
        seen = []
        for c in fk_cols:
            h = self._child(c)["header"]
            if h not in seen:
                seen.append(h)
        for rf in reps:
            if not getattr(rf, "fk_target", None):
                continue
            h = self._child_by_name(rf.fk_target)["header"]
            if h not in seen:
                seen.append(h)
        if not seen:
            return ""
        return "\n" + "\n".join('#include "{}"'.format(h) for h in seen)

    # -- child tables (map<K,V> and repeated), keyed by the parent's PK -----
    def _child_create_tables(self, children, columns, repeated=False):
        if not children:
            return ""
        pk = next((c for c in columns if c.pk), None)
        owner_sql = pk.sql_type if pk else self.backend.int_type
        parts = []
        for ch in children:
            if repeated and isinstance(ch, RepeatedComposedField):
                sql = self.backend.rep_composed_child_table(
                    ch.child_table, owner_sql,
                    [(c.name, c.sql_def()) for c in ch.columns])
            elif repeated:
                sql = self.backend.rep_child_table(
                    ch.child_table, owner_sql, ch.val_sql)
            else:
                sql = self.backend.map_child_table(
                    ch.child_table, owner_sql, ch.key_sql, ch.val_sql)
            parts.append('\n            db_ << "{}";'.format(
                sql.replace('"', '\\"')))
        return "".join(parts)

    def _child_drop_tables(self, children):
        return "".join(
            'db_ << "DROP TABLE IF EXISTS \\"{}\\";";\n            '.format(
                ch.child_table) for ch in children)

    def _child_remove(self, children):
        # remove()'s `id` parameter is the owner key
        blocks = []
        for ch in children:
            blocks.append(
                '            db_ << "DELETE FROM \\"{}\\" WHERE \\"owner\\" = :o"'
                ", ::soci::use(id);".format(ch.child_table))
        return "".join(b + "\n" for b in blocks)

    def _owner(self, id_col, dot=True):
        kind = id_col.kind if id_col else "int64"
        acc = ("msg.{}()".format(id_col.accessor) if dot
               else "msg->{}()".format(id_col.accessor)) if id_col else "0"
        return _local_ctype("int" if kind == "enum" else kind), acc

    def _map_write(self, maps, id_col, op):
        if not maps:
            return ""
        octype, oexpr = self._owner(id_col, dot=True)
        blocks = []
        for mf in maps:
            L = ["            {",
                 "                {} _owner = {};".format(octype, oexpr)]
            if op == "update":
                L.append(
                    '                db_ << "DELETE FROM \\"{}\\" WHERE '
                    '\\"owner\\" = :o", ::soci::use(_owner);'.format(
                        mf.child_table))
            L += [
                "                for (const auto& kv : {}) {{".format(
                    mf.entries("msg")),
                "                    {} _k = kv.first;".format(
                    _local_ctype(mf.key_kind)),
                "                    {} _v = kv.second;".format(
                    _local_ctype(mf.val_kind)),
                '                    db_ << "INSERT INTO \\"{}\\" (\\"owner\\", '
                '\\"key\\", \\"value\\") VALUES (:o, :k, :v)", '
                "::soci::use(_owner), ::soci::use(_k), ::soci::use(_v);".format(
                    mf.child_table),
                "                }",
                "            }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"

    def _map_read(self, maps, id_col):
        if not maps:
            return ""
        octype, oexpr = self._owner(id_col, dot=False)
        blocks = []
        for mf in maps:
            L = [
                "                {",
                "                    {} _k; {} _v;".format(
                    _local_ctype(mf.key_kind), _local_ctype(mf.val_kind)),
                "                    ::soci::indicator _ki, _vi;",
                "                    {} _owner = {};".format(octype, oexpr),
                '                    ::soci::statement _ms = (db_.prepare << '
                '"SELECT \\"key\\", \\"value\\" FROM \\"{}\\" WHERE '
                '\\"owner\\" = :o", ::soci::use(_owner), '
                "::soci::into(_k, _ki), ::soci::into(_v, _vi));".format(
                    mf.child_table),
                "                    _ms.execute();",
                "                    while (_ms.fetch()) {",
                "                        (*{})[_k] = _v;".format(mf.mutable()),
                "                    }",
                "                }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"

    def _rep_write(self, reps, id_col, op):
        if not reps:
            return ""
        octype, oexpr = self._owner(id_col, dot=True)
        blocks = []
        for rf in reps:
            if isinstance(rf, RepeatedComposedField):
                blocks.append(self._rep_composed_write(rf, octype, oexpr, op))
                continue
            L = ["            {",
                 "                {} _owner = {};".format(octype, oexpr)]
            if op == "update":
                L.append(
                    '                db_ << "DELETE FROM \\"{}\\" WHERE '
                    '\\"owner\\" = :o", ::soci::use(_owner);'.format(
                        rf.child_table))
            L += [
                "                long long _ord = 0;",
                "                for (const auto& rv : {}) {{".format(
                    rf.entries("msg")),
            ]
            if rf.fk_target:
                ch = self._child_by_name(rf.fk_target)
                child_op = ("if (!_c.create(rv)) return false;" if op == "create"
                            else "_c.update(rv);")
                L += [
                    "                    {} _c(db_);".format(ch["dao"]),
                    "                    " + child_op,
                    "                    long long _v = rv.{}();".format(ch["pk"]),
                ]
            else:
                L.append("                    {} _v = rv;".format(
                    _local_ctype(rf.val_kind)))
            L += [
                '                    db_ << "INSERT INTO \\"{}\\" (\\"owner\\", '
                '\\"ordinal\\", \\"value\\") VALUES (:o, :n, :v)", '
                "::soci::use(_owner), ::soci::use(_ord), ::soci::use(_v);".format(
                    rf.child_table),
                "                    ++_ord;",
                "                }",
                "            }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"

    def _rep_composed_write(self, rf, octype, oexpr, op):
        """Write loop for a RepeatedComposedField: one INSERT per element,
        columns = the target's own flattened scalar/enum fields."""
        L = ["            {",
             "                {} _owner = {};".format(octype, oexpr)]
        if op == "update":
            L.append(
                '                db_ << "DELETE FROM \\"{}\\" WHERE '
                '\\"owner\\" = :o", ::soci::use(_owner);'.format(rf.child_table))
        L += [
            "                long long _ord = 0;",
            "                for (const auto& rv : {}) {{".format(rf.entries("msg")),
        ]
        for i, c in enumerate(rf.columns):
            L.append("                    " + self._value_local("c", i, c, src="rv"))
        col_names = ", ".join('\\"{}\\"'.format(c.name) for c in rf.columns)
        placeholders = ", ".join(":c{}".format(i) for i in range(len(rf.columns)))
        uses = ", ".join("::soci::use(c{})".format(i) for i in range(len(rf.columns)))
        L += [
            '                    db_ << "INSERT INTO \\"{}\\" (\\"owner\\", '
            '\\"ordinal\\", {cols}) VALUES (:o, :n, {ph})", '
            "::soci::use(_owner), ::soci::use(_ord), {uses};".format(
                rf.child_table, cols=col_names, ph=placeholders, uses=uses),
            "                    ++_ord;",
            "                }",
            "            }",
        ]
        return "\n".join(L)

    def _rep_composed_read(self, rf, octype, oexpr):
        """Read loop for a RepeatedComposedField: one SELECT ordered by
        ordinal, adding+populating one element per row."""
        L = [
            "                {",
            "                    {} _owner = {};".format(octype, oexpr),
        ]
        for i, c in enumerate(rf.columns):
            L.append("                    " + self._read_local(i, c.kind))
        col_names = ", ".join('\\"{}\\"'.format(c.name) for c in rf.columns)
        intos = ", ".join("::soci::into(l{i}, n{i})".format(i=i)
                          for i in range(len(rf.columns)))
        L += [
            '                    ::soci::statement _rs = (db_.prepare << '
            '"SELECT {cols} FROM \\"{child}\\" WHERE \\"owner\\" = :o '
            'ORDER BY \\"ordinal\\"", ::soci::use(_owner), {intos});'.format(
                cols=col_names, child=rf.child_table, intos=intos),
            "                    _rs.execute();",
            "                    while (_rs.fetch()) {",
            "                        auto* _e = {};".format(rf.add_ptr_stmt()),
        ]
        for i, c in enumerate(rf.columns):
            if c.kind == "text":
                val = "n{i} == ::soci::i_ok ? l{i} : std::string()".format(i=i)
            elif c.kind == "enum":
                val = ("static_cast<::{et}>(n{i} == ::soci::i_ok ? l{i} : 0)"
                       .format(et=c.enum_type, i=i))
            else:
                val = "n{i} == ::soci::i_ok ? l{i} : 0".format(i=i)
            L.append("                        _e->set_{}({});".format(
                c.accessor, val))
        L += [
            "                    }",
            "                }",
        ]
        return "\n".join(L)

    def _rep_read(self, reps, id_col):
        if not reps:
            return ""
        octype, oexpr = self._owner(id_col, dot=False)
        blocks = []
        for rf in reps:
            if isinstance(rf, RepeatedComposedField):
                blocks.append(self._rep_composed_read(rf, octype, oexpr))
                continue
            is_text = (not rf.fk_target) and rf.val_kind == "text"
            valtype = "long long" if rf.fk_target else _local_ctype(rf.val_kind)
            vdecl = ("{} _v;".format(valtype) if is_text
                     else "{} _v = 0;".format(valtype))
            L = [
                "                {",
                "                    {} ::soci::indicator _vi;".format(vdecl),
                "                    {} _owner = {};".format(octype, oexpr),
                '                    ::soci::statement _rs = (db_.prepare << '
                '"SELECT \\"value\\" FROM \\"{}\\" WHERE \\"owner\\" = :o '
                'ORDER BY \\"ordinal\\"", ::soci::use(_owner), '
                "::soci::into(_v, _vi));".format(rf.child_table),
                "                    _rs.execute();",
                "                    while (_rs.fetch()) {",
            ]
            if rf.fk_target:
                ch = self._child_by_name(rf.fk_target)
                L += [
                    "                        {} _c(db_);".format(ch["dao"]),
                    "                        _c.read(_v, msg->add_{}());".format(
                        rf.field),
                ]
            else:
                L.append("                        {};".format(rf.add_stmt("_v")))
            L += [
                "                    }",
                "                }",
            ]
            blocks.append("\n".join(L))
        return "\n".join(blocks) + "\n"
