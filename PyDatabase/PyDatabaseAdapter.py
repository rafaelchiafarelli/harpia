"""python-target / py-database -- the Python target's database layer.

Copies the hand-written DB runtime (``PyDatabase/runtime/`` →
``harpia_runtime.db.*``) into the generated project. The per-message DAOs
(task 2a onward) are generated here too, from the same ``Database/model.py``
analysis and the same ``DbBackend`` object the C++ and Java targets use.
"""
import os

from Callback.callback_common import is_event_message
from Compliance.audit_common import PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC
from Compliance.context import DEFAULT_PROJECT
from Crypto.key_provider_common import (PY_ENCRYPTED_COLUMN_MODULE,
                                        PY_ENCRYPTED_COLUMN_RUNTIME_SRC,
                                        PY_KEY_PROVIDER_KMS_MODULE,
                                        PY_KEY_PROVIDER_KMS_RUNTIME_SRC,
                                        PY_KEY_PROVIDER_LOCAL_MODULE,
                                        PY_KEY_PROVIDER_LOCAL_RUNTIME_SRC,
                                        PY_KEY_PROVIDER_MODULE,
                                        PY_KEY_PROVIDER_RUNTIME_SRC)
from Database.DbRegistryAdapter import DbRegistryAdapter
from Database.backends import get_backend
from Database.model import (RepeatedComposedField, RepeatedField, analyze,
                            child_table_names, create_table_sql, map_fields,
                            repeated_fields, type_registry)
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_DAO_TEMPLATE = loadTemplate(__file__, "dao.py.tmpl")
_REGISTRY_TEMPLATE = loadTemplate(__file__, "registry.py.tmpl")
_MIGRATE_TEMPLATE = loadTemplate(__file__, "migrate.py.tmpl")
_DBIO_TEMPLATE = loadTemplate(__file__, "dbio.py.tmpl")
DBIO_EXT = "_dbio.py"
MIGRATE_EXT = "_migrate.py"
REGISTRY_FILE = "registry.py"
DAO_EXT = "_dao.py"

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("bind.py", "harpia_runtime.db.bind"),
    ("dao.py", "harpia_runtime.db.dao"),
    ("migrate.py", "harpia_runtime.db.migrate"),
    ("dbio.py", "harpia_runtime.db.dbio"),
    ("pool.py", "harpia_runtime.db.pool"),
)
#: copied only when some message has a phi column (with the crypto runtimes)
PHI_RUNTIME = ("phi.py", "harpia_runtime.db.phi")


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
        dbioDir = os.path.join(self.dest, "python", "harpia_generated", "dbio")
        os.makedirs(dbioDir, exist_ok=True)
        write_if_different(os.path.join(dbioDir, "__init__.py"),
                           '"""Generated bulk JSON/XML import/export, one module per table."""\n')
        written = 0
        if any(self._phi_columns(m) for m in self.messages
               if not getattr(m, "isEnum", False) and m.tableName):
            # like C++ CrudlAdapter: the column helper, the KeyProvider
            # interface + both persistent backends, and the audit sink
            for module, src in (
                    (PHI_RUNTIME[1], os.path.join(_RUNTIME_DIR, PHI_RUNTIME[0])),
                    (PY_ENCRYPTED_COLUMN_MODULE, PY_ENCRYPTED_COLUMN_RUNTIME_SRC),
                    (PY_KEY_PROVIDER_MODULE, PY_KEY_PROVIDER_RUNTIME_SRC),
                    (PY_KEY_PROVIDER_LOCAL_MODULE, PY_KEY_PROVIDER_LOCAL_RUNTIME_SRC),
                    (PY_KEY_PROVIDER_KMS_MODULE, PY_KEY_PROVIDER_KMS_RUNTIME_SRC),
                    (PY_AUDIT_SINK_MODULE, PY_AUDIT_SINK_RUNTIME_SRC)):
                copy_runtime_module(self.dest, src, module)
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
            write_if_different(os.path.join(
                dbioDir, "{}_{}{}".format(msg.name, msg.md5Hash, DBIO_EXT)),
                _DBIO_TEMPLATE.format(name=msg.name, hash=msg.md5Hash, table=msg.tableName,
                                      wrapper_lit=repr(msg.name + "_list")))
            written += 1
        write_if_different(os.path.join(self.outDir, REGISTRY_FILE), self._render_registry())
        self.log.print("copied {} DB runtime module(s); generated {} DAO(s) into {}".format(
            len(RUNTIMES), written, self.outDir))
        return None

    # -- DAO rendering ----------------------------------------------------------
    def _phi_columns(self, msg):
        """The columns C++ encrypts (CrudlAdapter: bindable scalar/enum or
        flattened-embed columns tagged ``phi``, never FK/child tables)."""
        columns, _ = analyze(msg, self.types, self.backend)
        return [c for c in columns if (c.bindable or c.embed) and not c.fk_table
                and getattr(c, "is_phi", False)]

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
        phi = [c for c in scalar if getattr(c, "is_phi", False)]
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
            # ORDER BY the key: stable pages on every dialect (as the C++ and
            # Java DAOs -- cpp-dao-list-order-DEFECT)
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
            runtime_imports=self._runtime_imports(children, phi),
            phi_import=("\nfrom harpia_runtime.db.phi import PhiDao" if phi else ""),
            base="PhiDao" if phi else "Dao",
            phi_doc=("\n\n    Encrypts its ``phi`` columns and audits every operation\n"
                     "    (:class:`~harpia_runtime.db.phi.PhiDao`).\n    " if phi else ""),
            phi_fields=("\n    PHI_FIELDS = {!r}".format(tuple(c.name for c in phi))
                        if phi else ""),
            event_import=self._event_import(msg),
            event_hook=self._event_hook(msg, phi),
            create_sql="".join("\n        {!r},".format(s) for s in create),
            drop_sql="".join("\n        {!r},".format(s) for s in drop),
            **{k: repr(v) for k, v in sql.items()})

    def _render_migration(self, msg):
        """Port of ``MigrationAdapter._render``: main-table steps (task 5a)
        and child-table rename / reap / evolve (task 5b). Same child sets as
        C++: repeated-scalar (no FK link table), map and repeated-composed
        fields; renames only for direct (non-embed-nested) fields, whose
        ``renamed_from`` C++ doesn't plumb either; the owner column type is
        the backend's ``int_type``, as in C++."""
        b, table = self.backend, msg.tableName
        columns, _ = analyze(msg, self.types, b)
        name = "<<NAME>>"
        reps = repeated_fields(msg, self.types, b)
        rep_scalars = [r for r in reps
                       if isinstance(r, RepeatedField) and not r.fk_target]
        rep_composed = [r for r in reps if isinstance(r, RepeatedComposedField)]
        maps = map_fields(msg, self.types, b)
        renamable = [ch for ch in rep_scalars + maps + rep_composed
                     if ch.renamed_from and not ch.embed]
        child_renames = tuple(
            ("{}__{}".format(table, ch.renamed_from), ch.child_table,
             b.rename_table("{}__{}".format(table, ch.renamed_from), ch.child_table))
            for ch in renamable)
        child_plans = tuple(
            [b.rep_child_plan(r.child_table, b.int_type, r.val_sql)
             for r in rep_scalars]
            + [b.map_child_plan(m.child_table, b.int_type, m.key_sql, m.val_sql)
               for m in maps]
            + [b.composed_child_plan(r.child_table, b.int_type,
                                     [(c.name, c.sql_type, c.sql_def())
                                      for c in r.columns])
               for r in rep_composed])
        return _MIGRATE_TEMPLATE.format(
            name=msg.name, hash=msg.md5Hash, table=table, dialect=b.name,
            hash_lit=repr(msg.md5Hash), table_lit=repr(table),
            pad=" " * (len("def migrate_{}(".format(msg.name))),
            version_table_sql=repr(b.version_table()),
            list_child_tables_sql=repr(b.list_tables_sql(table)),
            child_renames=repr(child_renames),
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
            child_current=repr(tuple(child_table_names(msg, self.types, b))),
            drop_table_sql=repr(b.drop_table(name, if_exists=False)),
            child_plans=repr(child_plans),
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

    @staticmethod
    def _event_import(msg):
        if not is_event_message(msg):
            return ""
        return ("from harpia_generated.events.{0}_{1}_events import (\n"
                "    {0}_channel,\n)\n").format(msg.name, msg.md5Hash)

    @staticmethod
    def _event_hook(msg, phi):
        """py-events task 2: an ``event`` message's DAO publishes each
        committed create/update (C++ CrudlAdapter's ``publish(msg)``); a
        phi+event one also records ``phi_event_onchange`` right after."""
        if not is_event_message(msg):
            return ""
        audit = ""
        if phi:
            audit = ('\n            self.audit_sink.record("phi_event_onchange", {!r}, {!r})'
                     .format(msg.tableName, ",".join(c.name for c in phi)))
        return ('\n\n    def _on_change(self, msg: {name}) -> None:\n'
                '        """OnChange: publish the written row to ``{name}_channel()``\n'
                '        once the transaction commits (never from read / list /\n'
                '        remove)."""\n\n'
                '        def fire() -> None:\n'
                '            {name}_channel().publish(msg){audit}\n\n'
                '        self._after_commit(fire)').format(name=msg.name, audit=audit)

    @staticmethod
    def _runtime_imports(children, phi):
        names = (["ChildTable"] if children else []) + ["Column"] + ([] if phi else ["Dao"])
        return ", ".join(names)

    def _column_spec(self, msg, col):
        path = tuple(self._exact_path(msg, col))
        fk = ""
        if col.fk_table:
            fk = ", fk={!r}".format(self._dao_ref(col.fk_target))
        if getattr(col, "is_phi", False) and not col.fk_table:
            fk += ", phi=True"
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
