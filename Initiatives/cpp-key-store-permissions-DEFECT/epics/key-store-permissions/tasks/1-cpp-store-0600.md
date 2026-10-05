## C++ LocalKeyProvider creates its store and .shred sidecar 0600

- **Depends on:** nothing.
- **Decision needed (planning, before code):** an existing store that is
  group/world-readable — tighten it with `chmod 0600` and continue, or refuse
  to load (fail-safe, like `LocalKeyProviderRefused`)? Bring both options to
  Rafael.
- **Deliverable:** `Crypto/runtime/harpia_key_provider_local.h` creates the
  store (and the `.shred` sidecar) with mode `0600` — POSIX `open(...,
  O_CREAT, 0600)` / `fchmod` before writing key bytes, so there is no window
  where the file exists with wider bits. Windows: document what is done (ACL)
  or that it is out of scope.
- **Tests:** `test_local_key_provider.py` (and `test_crypto_shred.py` for the
  sidecar): under `umask 022` the store and sidecar are `0600`; the
  existing-loose-store behavior per the decision above.
- **Docs:** `Crypto/CLAUDE.md` key-store note.
