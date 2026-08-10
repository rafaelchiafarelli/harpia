# SQLite (vendored)

- **Version:** 3.46.1 (amalgamation)
- **Source:** https://www.sqlite.org/2024/sqlite-amalgamation-3460100.zip
- **License:** public domain (https://www.sqlite.org/copyright.html)
- **Files:** `sqlite3.c`, `sqlite3.h`, `sqlite3ext.h`

Vendored in-tree (rather than installed from the system package manager) so the
exact third-party source used by harpia's Stage 8 database layer is tracked with
the project. The generated project's CMake / the tests compile `sqlite3.c`
directly.

To update: replace these files from a newer amalgamation zip and bump the
version above.
