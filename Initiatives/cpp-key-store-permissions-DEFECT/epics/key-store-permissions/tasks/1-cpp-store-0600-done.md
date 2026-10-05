## C++ LocalKeyProvider creates its store and .shred sidecar 0600; refuses loose ones

- **Depends on:** nothing.
- **Decision:** loose existing store/sidecar → refuse (see `../../README.md`).
- **1. Corroborate (red first):** add
  `UnitTests/test_local_key_provider.py::test_store_and_sidecar_are_0600_under_umask_022`
  — run the C++ driver under `umask 022`, create a KEK, shred one, then
  `stat` the store and `.shred`: assert `st_mode & 0o777 == 0o600`. Must
  **fail** on unmodified code (`std::ofstream` ~157/~206 → `0644`). If it
  passes, record the finding and stop.
- **2. Fix:** `Crypto/runtime/harpia_key_provider_local.h` — POSIX
  `open(path, O_WRONLY|O_CREAT|O_TRUNC (or O_APPEND), 0600)` + `fchmod(fd,
  0600)` before any key byte is written (no wider-bits window; `fchmod`
  covers a pre-existing file being rewritten). On load, `stat` the store and
  sidecar; any `0077` bit set → throw a new `LocalKeyStoreInsecure :
  std::runtime_error` naming the path and the octal mode. Windows (`_WIN32`):
  no POSIX modes — document it as out of scope in the header and
  `Crypto/CLAUDE.md`; the check is compiled out there.
- **3. Unit tests (required, kept):**
  - `test_store_and_sidecar_are_0600_under_umask_022` (above) — now green.
  - `test_loose_existing_store_is_refused` — `chmod 0644` an existing store
    → constructing/loading throws `LocalKeyStoreInsecure`; same for a loose
    `.shred` sidecar (`test_crypto_shred.py::test_loose_shred_sidecar_is_refused`).
  - Existing `test_keks_persist_across_instances_at_the_same_path` /
    `test_rotation_is_persisted` stay green (a rewrite keeps `0600`).
- **Golden:** the runtime is copied, not snapshotted — confirm no `golden/`
  move.
- **Docs:** `Crypto/CLAUDE.md` key-store note (mode, refusal, operator
  remedy).
