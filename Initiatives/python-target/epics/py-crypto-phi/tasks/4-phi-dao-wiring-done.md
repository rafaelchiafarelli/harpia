## Wire phi encrypt-on-write / decrypt-on-read + per-op audit into the generated DAOs

- **Depends on:** task 3; `py-database` task 2a (DAOs exist; 2b/2c if phi
  columns can sit in embeds/child tables, which mirror whatever C++
  `CrudlAdapter` supports today).
- **Contract:** for a message with a `Column.is_phi` column, the generated
  DAO (`<name>_<hash>_dao.py`) gains:
  - `key_provider=default_key_provider()` and `audit_sink=default_audit_sink()`
    constructor parameters;
  - `encrypt_field` on the create/update bind path (numeric/enum values
    stringified first, since the ciphertext stays in the column's existing
    type, as in C++);
  - `decrypt_field[_int|_float]` on read/list;
  - exactly one `record("phi_<op>", "<table>", "<phi col names>")` per
    CRUDL op (`phi_create`/`phi_read`/`phi_update`/`phi_delete`/`phi_list`).
    Names only. A not-found `read` audits nothing.

  A message with no phi column produces DAO output identical to before.
  The python backend copies the crypto runtime into
  `harpia_runtime/crypto/` only when a phi column exists.
- **Out of scope:** event OnChange audit (`py-events` task 2), redaction
  (already `py-serialization` task 4).
- **Tests:**
  - Generated-project test: a phi row's stored column starts with
    `enc:v1:`, reads back as plaintext, and records exactly one audit per
    op with no value anywhere.
  - Golden diff limited to phi messages' DAOs.
  - A g++-gated test: a C++ DAO writes a phi row to a SQLite file with a
    shared `LocalKeyProvider` store, and the Python DAO reads it (the full
    cross-read lives in `tri-language-interop` task 2; this is the minimal
    proof).
