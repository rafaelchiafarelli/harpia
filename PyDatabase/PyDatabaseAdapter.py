"""python-target / py-database -- the Python target's database layer.

Copies the hand-written DB runtime (``PyDatabase/runtime/`` →
``harpia_runtime.db.*``) into the generated project. The per-message DAOs
(task 2a onward) are generated here too, from the same ``Database/model.py``
analysis and the same ``DbBackend`` object the C++ and Java targets use.
"""
import os

from Database.backends import get_backend
from Database.model import analyze, create_table_sql, map_fields, repeated_fields, type_registry
from Logger.logger import logger
from PyAdapter.runtime_copy import copy_runtime_module
from Util.util import loadTemplate, write_if_different

_DAO_TEMPLATE = loadTemplate(__file__, "dao.py.tmpl")
DAO_EXT = "_dao.py"

_RUNTIME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime")

#: (source file under runtime/, destination module)
RUNTIMES = (
    ("bind.py", "harpia_runtime.db.bind"),
    ("dao.py", "harpia_runtime.db.dao"),
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
        written = 0
        for msg in self.messages:
            if getattr(msg, "isEnum", False) or not msg.tableName:
                continue
            text = self._render(msg)
            if text is None:
                continue
            write_if_different(os.path.join(
                self.outDir, "{}_{}{}".format(msg.name, msg.md5Hash, DAO_EXT)), text)
            written += 1
        self.log.print("copied {} DB runtime module(s); generated {} DAO(s) into {}".format(
            len(RUNTIMES), written, self.outDir))
        return None

    # -- DAO rendering ----------------------------------------------------------
    def _render(self, msg):
        columns, _notes = analyze(msg, self.types, self.backend)
        bound = [c for c in columns if c.bindable and not c.embed and not c.fk_table]
        pk = next((c for c in bound if c.pk), None)
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
            "list_sql": "SELECT {} FROM {}".format(sel, table),
            "list_page_sql": "SELECT {} FROM {} LIMIT {} OFFSET {}".format(
                sel, table, ph, ph),
        }
        create = [create_table_sql(msg, types=self.types, backend=self.backend)]
        drop = [self.backend.drop_table(msg.tableName)]
        return _DAO_TEMPLATE.format(
            name=msg.name, hash=msg.md5Hash, table=msg.tableName,
            dialect=self.backend.name, placeholder=ph,
            deferred=", ".join(deferred) if deferred else "none",
            table_lit=repr(msg.tableName), pk_lit=repr(pk.name),
            columns="".join("\n        Column({!r}, ({!r},)),".format(c.name, c.name)
                            for c in bound),
            create_sql="".join("\n        {!r},".format(s) for s in create),
            drop_sql="".join("\n        {!r},".format(s) for s in drop),
            **{k: repr(v) for k, v in sql.items()})

    def _deferred(self, msg, columns):
        """Columns / child tables the C++ DAO persists that this DAO doesn't
        yet (embedded sub-fields and FKs: task 2b; maps / repeated: 2c)."""
        out = [c.name for c in columns
               if (c.embed or c.fk_table) and (c.bindable or c.embed or c.fk_table)]
        out += [ch.child_table for ch in map_fields(msg, self.types, self.backend)]
        out += [ch.child_table for ch in repeated_fields(msg, self.types, self.backend)]
        return out
