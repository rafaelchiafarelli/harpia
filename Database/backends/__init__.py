"""DB-backend registry for harpia's Stage-8 database layer.

Select a dialect with :func:`get_backend` (default ``"sqlite"``). ``main.py``
resolves the name once -- from a ``.harpia`` directive or the
``HARPIA_DB_BACKEND`` env var -- and threads the resulting :class:`DbBackend`
into SqlAdapter / CrudlAdapter / MigrationAdapter. See ``base.py`` for the
interface and why the rest of the generated C++ is dialect-free (SOCI).
"""
from Database.backends.base import (DbBackend, SOCI_SESSION_TYPE,
                                    SOCI_CORE_HEADER)
from Database.backends.sqlite import SqliteBackend

DEFAULT_BACKEND = "sqlite"

# name -> singleton (dialects are stateless).
_REGISTRY = {b.name: b for b in (SqliteBackend(),)}


def get_backend(name=None):
    """Return the :class:`DbBackend` for ``name`` (or the default). Raises
    ``ValueError`` on an unknown name so a bad ``.harpia`` directive /
    ``HARPIA_DB_BACKEND`` fails loudly at generation time."""
    key = (name or DEFAULT_BACKEND).strip().lower()
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ValueError("unknown harpia DB backend {!r}; known: {}".format(
            name, ", ".join(sorted(_REGISTRY))))


def register(backend):
    """Register an additional backend (e.g. PostgresBackend in a later slice)."""
    if not isinstance(backend, DbBackend):
        raise TypeError("backend must be a DbBackend, got {!r}".format(backend))
    _REGISTRY[backend.name] = backend


__all__ = ["DbBackend", "SqliteBackend", "get_backend", "register",
           "DEFAULT_BACKEND", "SOCI_SESSION_TYPE", "SOCI_CORE_HEADER"]
