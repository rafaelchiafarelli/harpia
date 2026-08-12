"""DB-backend (SQL dialect) abstraction for harpia's Stage-8 database layer.

Everything that actually differs between databases lives behind ``DbBackend``:

  * **DDL**        -- scalar column types, PRIMARY KEY syntax, CREATE/DROP TABLE,
                      the map/repeated child tables.
  * **migration**  -- how to list a live table's columns, ADD COLUMN, and stamp
                      the schema version (upsert).
  * **session**    -- the SOCI backend factory + header used at the ONE place the
                      connection is opened.

Everything *else* in the generated C++ is dialect-free, because the DAO is
emitted against **SOCI** (`use()` / `into()` / `rowset`, `:name` placeholders),
which is uniform across SQLite / PostgreSQL / MySQL. In particular the whole
INSERT/SELECT/UPDATE/DELETE + parameter-binding surface is NOT the backend's
concern -- it is one dialect-free template in CrudlAdapter. That is the entire
reason "Route B (SOCI)" is far less code than a per-backend C-API rewrite: the
divergence collapses to the handful of methods below.

Design constraint: this module has **no harpia dependencies** (it must never
import ``Database.model``). It operates on primitive inputs -- scalar type
tokens, identifier strings, already-resolved SQL type strings, ``(name, def)``
column pairs -- and returns SQL / C++ text. That keeps every dialect trivially
unit-testable in isolation and lets ``model.py`` depend on the backend (one
direction only, no cycle).

Identifiers are emitted double-quoted everywhere (``"table"``). Postgres folds
unquoted identifiers to lower-case, so quoting is what makes the SQLite and
Postgres output case-compatible; harpia already quotes everywhere.
"""
from abc import ABC, abstractmethod


def _esc(sql):
    """Escape a SQL string for embedding in a C++ string literal. Shared by
    dialect methods (like drop_column_dynamic/retype_block) that return
    ready-made C++ rather than a plain SQL string for the caller to escape."""
    return sql.replace('"', '\\"')


# The generated DAO / REST / SOAP / gRPC headers all take a `soci::session&`.
# This type is IDENTICAL for every SOCI backend -- only the factory symbol used
# to OPEN a session (``soci_backend_symbol``) is backend-specific. So the only
# backend-aware line in an entire generated project is the session-open site.
SOCI_SESSION_TYPE = "::soci::session"
SOCI_CORE_HEADER = "soci/soci.h"


class DbBackend(ABC):
    # -- identity -------------------------------------------------------------
    #: harpia backend id, as used by the ``.harpia`` directive / HARPIA_DB_BACKEND.
    name: str = ""
    #: SOCI backend factory name, e.g. "sqlite3" / "postgresql".
    soci_backend: str = ""

    @property
    @abstractmethod
    def soci_backend_symbol(self) -> str:
        """C++ SOCI backend factory symbol (e.g. ``::soci::sqlite3``). Used ONLY
        where a session is opened (the demo/main), never inside a generated DAO."""

    @property
    @abstractmethod
    def soci_backend_header(self) -> str:
        """SOCI backend header for the session-open site
        (e.g. ``soci/sqlite3/soci-sqlite3.h``)."""

    # -- DDL: types -----------------------------------------------------------
    @abstractmethod
    def sql_type(self, token: str) -> str:
        """SQL column type for a harpia scalar token
        (``INT32`` / ``INT64`` / ``BOOL`` / ``FLOAT`` / ``STRING``).

        Raises ``KeyError`` for an unknown token; callers treat that as the
        existing "unsupported type (skipped)" note. The neutral C++ bind *kind*
        (``int`` / ``int64`` / ``double`` / ``text``) that used to sit beside
        these in ``model._SCALARS`` is NOT a dialect concern and stays in
        ``model.py``."""

    @property
    @abstractmethod
    def int_type(self) -> str:
        """SQL type for the integer key columns the model synthesises itself:
        enum-value columns, singular-FK child-PK columns, and a child table's
        ``owner`` column when no explicit PK type is known."""

    # -- DDL: columns & tables ------------------------------------------------
    @abstractmethod
    def column_def(self, sql_type: str, *, pk: bool = False,
                   required: bool = False, unique: bool = False) -> str:
        """One column's type + constraints (replaces the old
        ``Column.sql_def()``). ``sql_type`` is already resolved (via
        :meth:`sql_type` / :attr:`int_type`)."""

    @abstractmethod
    def create_table(self, table: str, columns, if_not_exists: bool = True) -> str:
        """CREATE TABLE. ``columns`` is an iterable of ``(name, column_def)``
        pairs. Returns canonical single-line SQL with double-quoted identifiers.
        Callers that embed the result in a C++ string literal escape the quotes
        themselves (as CrudlAdapter does today)."""

    @abstractmethod
    def drop_table(self, table: str, if_exists: bool = True) -> str:
        """DROP TABLE."""

    @abstractmethod
    def map_child_table(self, child: str, owner_type: str, key_type: str,
                        val_type: str, if_not_exists: bool = True) -> str:
        """Child table for a ``map<K,V>`` field: columns ``(owner, key, value)``
        with ``PRIMARY KEY(owner, key)``."""

    @abstractmethod
    def rep_child_table(self, child: str, owner_type: str, val_type: str,
                        if_not_exists: bool = True) -> str:
        """Child table for a repeated field: columns ``(owner, ordinal, value)``
        with ``PRIMARY KEY(owner, ordinal)``."""

    @abstractmethod
    def rep_composed_child_table(self, child: str, owner_type: str, columns,
                                 if_not_exists: bool = True) -> str:
        """Child table for a repeated field whose target is a table-less
        composed message: columns ``(owner, ordinal, <one per flattened
        field>)`` with ``PRIMARY KEY(owner, ordinal)``. ``columns`` is an
        iterable of ``(name, sql_type)`` pairs (the target's own flattened
        scalar/enum fields, unprefixed)."""

    # -- migration / introspection -------------------------------------------
    @abstractmethod
    def version_table(self) -> str:
        """DDL for the ``_harpia_schema_version`` bookkeeping table."""

    @abstractmethod
    def list_columns_sql(self, table: str) -> str:
        """A query whose first (and only) selected column is the NAME of each
        column the live ``table`` currently has. Read uniformly by the SOCI
        migration code, so PRAGMA-vs-information_schema never leaks into the
        generated C++."""

    @abstractmethod
    def add_column(self, table: str, name: str, column_def: str) -> str:
        """Additive migration: ``ALTER TABLE ... ADD COLUMN``."""

    @abstractmethod
    def rename_column(self, table: str, old: str, new: str) -> str:
        """Non-additive migration: ``ALTER TABLE ... RENAME COLUMN``. Both
        names are known at generation time (from the DSL's
        ``renamed_from[<old>]`` field modifier), unlike
        :meth:`drop_column_dynamic` below."""

    @abstractmethod
    def drop_column_dynamic(self, table: str, name_expr: str) -> str:
        """Non-additive migration: a C++ EXPRESSION (not a complete SQL
        literal, unlike every other method here) that concatenates a
        RUNTIME-known column name (``name_expr``, a C++ ``std::string``
        expression) into a ``DROP COLUMN`` statement for ``table``. The
        dropped column's name is only known once migration runs against a
        live database -- there is no schema history to diff against at
        generation time, only the live table's actual columns."""

    @abstractmethod
    def stamp_version(self, table: str, version: str) -> str:
        """Upsert ``(table, version)`` into ``_harpia_schema_version``."""

    @abstractmethod
    def list_column_types_sql(self, table: str) -> str:
        """A query whose first two selected columns are (NAME, TYPE) of each
        column the live ``table`` currently has. Read uniformly by the
        generated migration C++ into a ``have_types`` map, to detect a column
        whose live type no longer matches what the current schema declares
        for that same name -- unlike a rename, a type change needs no DSL
        marker: the name is unchanged, so a mismatch is unambiguous."""

    @abstractmethod
    def retype_column_dynamic(self, table: str, columns) -> str:
        """Non-additive migration: C++ STATEMENTS (not a single SQL string,
        unlike most methods here -- same "backend returns C++" precedent as
        :meth:`drop_column_dynamic`) that bring every column in ``table`` to
        the type the current schema declares, guarded by the runtime
        ``have_types`` map the caller has already populated (via
        :meth:`list_column_types_sql`) so a matching column is left alone.
        ``columns`` is an iterable of ``(name, sql_type, column_def)``
        triples for every column :func:`Database.model.analyze` returns
        (``column_def`` -- the full DDL fragment from ``Column.sql_def()``
        -- is needed only by backends whose fix requires rebuilding the
        whole table, e.g. SQLite has no ``ALTER COLUMN ... TYPE``; ignored
        otherwise)."""

    # -- convenience ----------------------------------------------------------
    def __repr__(self):
        return "<DbBackend {!r} (soci:{})>".format(self.name, self.soci_backend)
