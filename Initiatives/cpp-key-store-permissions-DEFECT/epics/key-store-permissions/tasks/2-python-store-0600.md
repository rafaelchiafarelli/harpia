## Python LocalKeyProvider mirrors task 1

- **Depends on:** task 1 (same behavior, same decision).
- **Deliverable:** `Crypto/runtime/python/key_provider_local.py` creates the
  store and `.shred` sidecar with `os.open(path, flags, 0o600)` (no
  wider-bits window) and applies task 1's existing-loose-store rule.
- **Golden:** regenerate `UnitTests/golden_python/` if the runtime is
  snapshotted there; review the diff is only this change.
- **Tests:** `test_py_key_provider_backends.py`: same mode assertions as task
  1; a store written by C++ is accepted by Python and the reverse.
- **Docs:** drop the "not restricted to 0600 (parity)" note from the
  python-target log entry / `Crypto/CLAUDE.md`.
