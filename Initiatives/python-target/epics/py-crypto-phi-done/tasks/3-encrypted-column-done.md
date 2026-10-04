## `enc:v1:` encrypted-column helpers, byte-compatible with C++

- **Depends on:** tasks 1–2.
- **Contract:** `harpia_runtime/crypto/encrypted_column.py`, a port of
  `harpia_encrypted_column.h`.
  - `encrypt_field(kp, plaintext) -> str` runs generate_dek → seal →
    wrap_dek, frames `{kek_version, wrapped_dek, ciphertext}`, and emits
    `"enc:v1:"` + hex. The framing is identical to C++.
  - `decrypt_field` plus `decrypt_field_int` / `decrypt_field_float`
    (numeric phi). An unrecoverable value returns `0` / `""` and never
    raises (Rule 5).
  - `default_key_provider()` is a process-wide `InMemoryKeyProvider`.
- **Bar:** a value encrypted by C++ with a shared `LocalKeyProvider` store
  decrypts in Python, and the reverse. This is what lets a C++ server and
  a Python client share one SQLite file with phi columns
  (`tri-language-interop` task 2).
- **Out of scope:** DAO wiring (task 4).
- **Tests:**
  - Unit tests (round-trip; numeric phi; a tampered/unknown value
    returns `0`/`""` without raising).
  - A g++-gated cross-language test in both directions over a shared
    store.
