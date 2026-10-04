"""Schema migration engine for the generated Python migrations (port of the
C++ ``migrate_<name>`` in ``Database/templates/migrate.h.tmpl``).

A generated ``harpia_generated/migrate/<name>_<hash>_migrate.py`` holds a
:class:`MigrationSpec` (every SQL statement comes from the same
``DbBackend`` the C++ migration uses, including its migration *plans*) and
calls :func:`migrate`. The steps run in the C++ order:

1. ensure ``_harpia_schema_version``;
2. list the live ``<table>__*`` child tables and apply child-table renames
   (``renamed_from`` on a repeated/map field) before anything is created;
3. ensure the table and its child tables exist;
4. RENAME ``renamed_from`` columns, correcting the introspected column set;
5. ADD missing non-key columns;
6. call ``data_transform(conn)`` -- after ADD (new destination columns
   exist) and before DROP (retiring source columns are still readable),
   the order the split-column case depends on;
7. DROP live columns the current schema doesn't declare;
8. RETYPE columns whose live type differs (PostgreSQL ``ALTER COLUMN ..
   TYPE``, SQLite rebuild-and-copy);
9. reap child tables the schema no longer declares, then evolve each
   surviving one (``value`` / ``key`` retype, repeated-composed
   add/drop/retype);
10. stamp the version.

Like the C++ migration this is an implicit diff with no schema history: any
unrecognized live column or child table is dropped. Unlike C++ (which
returns ``false``), errors raise; the whole migration is one transaction.
``data_transform`` runs inside it and should be idempotent, since
``migrate_<name>`` may run on every startup.
"""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from harpia_runtime.db.dao import Connection, Dao

#: a backend migration plan (see ``DbBackend.retype_plan`` & co.)
Plan = dict[str, Any]

_NAME = "<<NAME>>"


@dataclass(frozen=True)
class MigrationSpec:
    """Everything one table's migration needs, generated per message."""

    table: str
    version: str
    version_table_sql: str
    list_child_tables_sql: str
    #: ``(old, new, sql)`` child-table renames
    child_renames: tuple[tuple[str, str, str], ...]
    list_columns_sql: str
    #: ``(old, new, sql)`` column renames
    renames: tuple[tuple[str, str, str], ...]
    #: ``(column, sql)`` additive ALTERs (non-key columns)
    adds: tuple[tuple[str, str], ...]
    current_columns: tuple[str, ...]
    #: ``ALTER .. DROP COLUMN`` with ``<<NAME>>`` for the column
    drop_column_sql: str
    retype: Plan
    #: every child table the schema declares; ``None`` skips the reap
    child_current: tuple[str, ...] | None
    #: ``DROP TABLE`` with ``<<NAME>>`` for the table
    drop_table_sql: str
    child_plans: tuple[Plan, ...]
    stamp_sql: str


def _names(cur: Any, sql: str) -> set[str]:
    cur.execute(sql)
    return {row[0] for row in cur.fetchall() if row[0] is not None}


def _types(cur: Any, sql: str) -> dict[str, str]:
    cur.execute(sql)
    return {n: t for n, t in cur.fetchall() if n is not None and t is not None}


def run_plan(cur: Any, plan: Plan) -> None:
    """Apply one backend migration plan against the live table."""
    live = _types(cur, plan["types_sql"])
    force = False
    if "adds" in plan:  # a repeated-composed child table
        if not live:
            return
        for column, sql in plan["adds"]:
            if column not in live:
                cur.execute(sql)
        strays = sorted(c for c in live if c not in set(plan["keep"]))
        if plan["strays"] == "drop":
            for column in strays:
                cur.execute(plan["drop_sql"].replace(_NAME, column))
                del live[column]
        else:
            force = bool(strays)
    for index, (conditions, statements) in enumerate(plan["steps"]):
        drifted = any(c in live and live[c] != want for c, want in conditions)
        if drifted or (index == 0 and force):
            for sql in statements:
                cur.execute(sql)


def migrate(conn: Connection, spec: MigrationSpec, dao: type[Dao[Any]],
            data_transform: Callable[[Connection], None] | None = None) -> bool:
    """Bring ``spec.table`` (and its child tables) up to ``spec.version``.

    Returns:
        ``True``. A database error raises and rolls the migration back.
    """
    cur = conn.cursor()
    if getattr(conn, "in_transaction", None) is False:
        # sqlite3 runs DDL outside its implicit transactions; open one so the
        # whole migration (DDL included) commits or rolls back as a unit.
        # psycopg already wraps DDL in its transaction.
        cur.execute("BEGIN")
    try:
        cur.execute(spec.version_table_sql)
        child_have = _names(cur, spec.list_child_tables_sql)
        for old, new, sql in spec.child_renames:
            if old in child_have and new not in child_have:
                cur.execute(sql)
                child_have.discard(old)
                child_have.add(new)
        for sql in dao.CREATE_TABLE_SQL:
            cur.execute(sql)
        have = _names(cur, spec.list_columns_sql)
        for old, new, sql in spec.renames:
            if old in have and new not in have:
                cur.execute(sql)
                have.discard(old)
                have.add(new)
        for column, sql in spec.adds:
            if column not in have:
                cur.execute(sql)
        if data_transform is not None:
            data_transform(conn)
        current = set(spec.current_columns)
        for column in sorted(have):
            if column not in current:
                cur.execute(spec.drop_column_sql.replace(_NAME, column))
        run_plan(cur, spec.retype)
        if spec.child_current is not None:
            keep = set(spec.child_current)
            for table in sorted(child_have):
                if table not in keep:
                    cur.execute(spec.drop_table_sql.replace(_NAME, table))
        for plan in spec.child_plans:
            run_plan(cur, plan)
        cur.execute(spec.stamp_sql)
    except BaseException:
        conn.rollback()
        raise
    conn.commit()
    return True
