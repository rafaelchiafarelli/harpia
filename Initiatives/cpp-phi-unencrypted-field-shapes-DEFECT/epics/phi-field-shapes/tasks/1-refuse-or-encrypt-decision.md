## Decide, then (option a) refuse phi on unencrypted shapes

- **Depends on:** Rafael's decision in `../../README.md`.
- **1. Corroborate (red first):** a probe `.harpia` (temp dir, not the
  fixture) with `phi` on an enum field, an embedded sub-field, a repeated
  scalar and a map; a test asserting each such column is stored `enc:v1:`
  (C++ and Python DAO) — fails today (plaintext).
- **2. Deliverable (option a):** generation fails with a named error for
  each unsupported `phi` shape (one place, shared by every language
  target); option (b): no code here, go to task 2.
- **3. Unit test (kept):** the probe schema → the named error per shape; a
  schema with only scalar phi still generates.
