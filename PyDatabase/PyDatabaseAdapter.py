"""python-target / py-database -- the Python target's database layer.

Copies the hand-written DB runtime (``PyDatabase/runtime/`` →
``harpia_runtime.db.*``) into the generated project. The per-message DAOs
(task 2a onward) are generated here too, from the same ``Database/model.py``
analysis and the same ``DbBackend`` object the C++ and Java targets use.
"""
import os

from Compliance.context import DEFAULT_PROJECT
from Database.DbRegistryAdapter import DbRegistryAdapter
from Database.backends import get_backend
from Database.model import (RepeatedComposedField, analyze, create_table_sql, map_fields,
                            repeated_fields, type_registry)
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_DAO_TEMPLATE = loadTemplate(__file__, "dao.py.tmpl")
_REGISTRY_TEMPLATE = loadTemplate(__file__, "registry.py.tmpl")
_MIGRATE_TEMPLATE = loadTemplate(__file__, "migrate.py.tmpl")
MIGRATE_EXT = "_migrate.py"
REGISTRY_FILE = "registry.py"
DAO_EXT = "_dao.py"

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("bind.py", "harpia_runtime.db.bind"),
    ("dao.py", "harpia_runtime.db.dao"),
    ("migrate.py", "harpia_runtime.db.migrate"),
)


class PyDatabaseAdapter:
    def __init__(self, messages, dest, backend=None, compliance=None) -> None:
        self.compliance = compliance
        self.messages = messages
        self.dest = dest
        self.backend = backend or get_backend()
        self.types = type_registry(messages)
        self.outDir = os.path.join(dest, "python", "harpia_generated", "db")
        self.log = logger(outFile=None, moduleName="PyDatabaseAdapter")

    def Process(self):
        for src, module in RUNTIMES:
            copy_runtime_module(self.dest, os.path.join(_RUNTIME_DIR, src), module)
        os.makedirs(self.outDir, exist_ok=True)
        write_if_different(os.path.join(self.outDir, "__init__.py"),
                           '"""Generated CRUDL data-access objects, one module per table."""\n')
        migrateDir = os.path.join(self.dest, "python", "harpia_generated", "migrate")
        os.makedirs(migrateDir, exist_ok=True)
        write_if_different(os.path.join(migrateDir, "__init__.py"),
                           '"""Generated schema migrations, one module per table."""\n')
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            text = self._render(msg)
            if text is None:
                continue
            write_if_different(os.path.join(
                self.outDir, "{}_{}{}".format(msg.name, msg.md5Hash, DAO_EXT)), text)
            write_if_different(os.path.join(
                migrateDir, "{}_{}{}".format(msg.name, msg.md5Hash, MIGRATE_EXT)),
                self._render_migration(msg))
            written += 1
        write_if_different(os.path.join(self.outDir, REGISTRY_FILE), self._render_registry())
        self.log.print("copied {} DB runtime module(s); generated {} DAO(s) into {}".format(
            len(RUNTIMES), written, self.outDir))
        return None

    # -- DAO rendering ----------------------------------------------------------
    def _render(self, msg):
        columns, _notes = analyze(msg, self.types, self.backend)
        # C++ CrudlAdapter order: scalar/enum/embedded columns, then FKs
        scalar = [c for c in columns if (c.bindable or c.embed) and not c.fk_table]
        fks = [c for c in columns if c.fk_table]
        bound = scalar + fks
        pk = next((c for c in scalar if c.pk), None)
        if pk is None:
            self.log.print("{}: no ID_ primary key, no Python DAO".format(msg.name))
            return None
        deferred = self._deferred(msg, columns)
        ph = self.backend.param_placeholder()
        q = '"{}"'.format
        names = [c.name for c in bound]
        non_pk = [c.name for c in bound if not c.pk]
        sel = ", ".join(q(n) for n in names)
        table = q(msg.tableName)
        sql = {
            "insert_sql": "INSERT INTO {} ({}) VALUES ({})".format(
                table, sel, ", ".join([ph] * len(names))),
            "select_sql": "SELECT {} FROM {} WHERE {} = {}".format(
                sel, table, q(pk.name), ph),
            "update_sql": "UPDATE {} SET {} WHERE {} = {}".format(
                table, ", ".join("{} = {}".format(q(n), ph) for n in non_pk),
                q(pk.name), ph),
            "delete_sql": "DELETE FROM {} WHERE {} = {}".format(table, q(pk.name), ph),
            # ORDER BY the key: stable pages on every dialect (the C++ DAO has
            # no ORDER BY; SQLite happens to return rowid = key order)
            "list_sql": "SELECT {} FROM {} ORDER BY {}".format(sel, table, q(pk.name)),
            "list_page_sql": "SELECT {} FROM {} ORDER BY {} LIMIT {} OFFSET {}".format(
                sel, table, q(pk.name), ph, ph),
        }
        maps = map_fields(msg, self.types, self.backend)
        reps = repeated_fields(msg, self.types, self.backend)
        children = [self._child_spec(msg, ch, "map", ph) for ch in maps]
        children += [self._child_spec(msg, ch, "rep", ph) for ch in reps]
        create = [create_table_sql(msg, types=self.types, backend=self.backend)]
        create += [self._child_ddl(ch, pk.sql_type) for ch in maps + reps]
        drop = [self.backend.drop_table(ch.child_table) for ch in maps + reps]
        drop.append(self.backend.drop_table(msg.tableName))
        return _DAO_TEMPLATE.format(
            name=msg.name, hash=msg.md5Hash, table=msg.tableName,
            dialect=self.backend.name, placeholder=ph,
            deferred=", ".join(deferred) if deferred else "none",
            table_lit=repr(msg.tableName), pk_lit=repr(pk.name),
            columns="".join("\n        " + self._column_spec(msg, c) for c in bound),
            children="".join(children),
            runtime_imports=("ChildTable, Column, Dao" if children else "Column, Dao"),
            create_sql="".join("\n        {!r},".format(s) for s in create),
            drop_sql="".join("\n        {!r},".format(s) for s in drop),
            **{k: repr(v) for k, v in sql.items()})

    def _render_migration(self, msg):
        """Port of MigrationAdapter's main-table steps (task 5a). Child-table
        steps (rename / reap / evolve) are task 5b: until then the reap is
        off (``child_current=None``) and no child plan runs."""
        b, table = self.backend, msg.tableName
        columns, _ = analyze(msg, self.types, b)
        name = "<<NAME>>"
        return _MIGRATE_TEMPLATE.format(
            name=msg.name, hash=msg.md5Hash, table=table, dialect=b.name,
            hash_lit=repr(msg.md5Hash), table_lit=repr(table),
            pad=" " * (len("def migrate_{}(".format(msg.name))),
            version_table_sql=repr(b.version_table()),
            list_child_tables_sql=repr(b.list_tables_sql(table)),
            child_renames="()",
            list_columns_sql=repr(b.list_columns_sql(table)),
            renames=repr(tuple((c.renamed_from, c.name,
                                b.rename_column(table, c.renamed_from, c.name))
                               for c in columns if getattr(c, "renamed_from", None))),
            adds=repr(tuple((c.name, b.add_column(table, c.name, c.sql_type))
                            for c in columns if not c.pk)),
            current_columns=repr(tuple(c.name for c in columns)),
            drop_column_sql=repr(b.drop_column_sql(table, name)),
            retype=repr(b.retype_plan(table, [(c.name, c.sql_type, c.sql_def())
                                              for c in columns])),
            child_current="None",
            drop_table_sql=repr(b.drop_table(name, if_exists=False)),
            child_plans="()",
            stamp_sql=repr(b.stamp_version(table, msg.md5Hash)))

    def _render_registry(self):
        """The Python port of DbRegistryAdapter's header: the same entries
        and conflict notes (``DbRegistryAdapter._entries``)."""
        project = getattr(self.compliance, "project", None) or DEFAULT_PROJECT
        entries, conflicts = DbRegistryAdapter(self.messages, self.dest,
                                               compliance=self.compliance)._entries()
        rows = "".join("\n    RegistryEntry({!r}, Visibility.{}, {!r}),".format(
            table, vis, project) for table, vis in entries)
        notes = "".join(
            "# note: table {!r} is also declared {} by message {!r} -- kept the "
            "first declaration below\n".format(t, v, n) for t, n, v in conflicts)
        return _REGISTRY_TEMPLATE.format(project=repr(project), notes=notes,
                                         rows=rows + ("\n" if rows else ""))

    def _child_ddl(self, ch, owner_sql):
        if isinstance(ch, RepeatedComposedField):
            return self.backend.rep_composed_child_table(
                ch.child_table, owner_sql, [(c.name, c.sql_def()) for c in ch.columns])
        if hasattr(ch, "key_sql"):
            return self.backend.map_child_table(ch.child_table, owner_sql,
                                                ch.key_sql, ch.val_sql)
        return self.backend.rep_child_table(ch.child_table, owner_sql, ch.val_sql)

    def _child_spec(self, msg, ch, family, ph):
        q = '"{}"'.format
        t = q(ch.child_table)
        steps = ([ch.embed] if ch.embed else []) + [ch.field]
        path = tuple(self._walk(msg, steps))
        delete = "DELETE FROM {} WHERE {} = {}".format(t, q("owner"), ph)
        extra = ""
        if family == "map":
            kind = "map"
            insert = "INSERT INTO {} ({}, {}, {}) VALUES ({})".format(
                t, q("owner"), q("key"), q("value"), ", ".join([ph] * 3))
            select = "SELECT {}, {} FROM {} WHERE {} = {}".format(
                q("key"), q("value"), t, q("owner"), ph)
        elif isinstance(ch, RepeatedComposedField):
            kind = "composed"
            elem = self._element_type(msg, steps)
            cols = ", ".join(q(c.name) for c in ch.columns)
            insert = "INSERT INTO {} ({}, {}, {}) VALUES ({})".format(
                t, q("owner"), q("ordinal"), cols, ", ".join([ph] * (2 + len(ch.columns))))
            select = "SELECT {} FROM {} WHERE {} = {} ORDER BY {}".format(
                cols, t, q("owner"), ph, q("ordinal"))
            extra = ", columns=({},)".format(", ".join(
                "Column({!r}, {!r})".format(c.name, tuple(self._walk(elem, [c.child_accessor])))
                for c in ch.columns))
        else:
            kind = "repeated"
            insert = "INSERT INTO {} ({}, {}, {}) VALUES ({})".format(
                t, q("owner"), q("ordinal"), q("value"), ", ".join([ph] * 3))
            select = "SELECT {} FROM {} WHERE {} = {} ORDER BY {}".format(
                q("value"), t, q("owner"), ph, q("ordinal"))
            if ch.fk_target:
                extra = ", fk={!r}".format(self._dao_ref(ch.fk_target))
        return ("\n        ChildTable(\n            {!r}, {!r},\n            {!r},"
                "\n            {!r},\n            {!r}{}),").format(
                    kind, path, insert, select, delete, extra)

    def _element_type(self, msg, steps):
        current = msg
        for step in steps:
            var = next(v for v in current.variables if v.name.lower() == step)
            current = self.types[var.type[1]]["msg"] if var.type[0] == "ID" else current
        return current

    def _column_spec(self, msg, col):
        path = tuple(self._exact_path(msg, col))
        fk = ""
        if col.fk_table:
            fk = ", fk={!r}".format(self._dao_ref(col.fk_target))
        return "Column({!r}, {!r}{}),".format(col.name, path, fk)

    def _dao_ref(self, message_name):
        target = next(m for m in self.messages if m.name == message_name)
        return "harpia_generated.db.{0}_{1}_dao:{0}_dao".format(
            target.name, target.md5Hash)

    def _exact_path(self, msg, col):
        """The column's attribute path with the exact ``.proto`` field names
        (``Column.embed`` / ``child_accessor`` hold C++'s lowercased
        accessors)."""
        if col.embed:
            return self._walk(msg, list(col.embed) + [col.child_accessor])
        return [col.name]

    def _walk(self, msg, steps):
        path, current = [], msg
        for step in steps:
            var = next(v for v in current.variables if v.name.lower() == step)
            path.append(var.name)
            if var.type[0] == "ID" and var.type[1] in self.types:
                current = self.types[var.type[1]]["msg"]
        return path

    def _deferred(self, msg, columns):
        """What the C++ DAO persists that this DAO doesn't (empty since task
        2c; kept so a future gap is listed in the module, never silent)."""
        return []
