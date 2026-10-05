## Python LocalKeyProvider mirrors task 1

- **Depends on:** task 1 (same behavior, same decision).
- **1. Corroborate (red first):** add
  `UnitTests/test_py_key_provider_backends.py::test_local_store_and_sidecar_are_0600`
  — under `os.umask(0o022)`, create + shred → assert both files are `0600`.
  Must **fail** on unmodified code (`open(self._path, "w")` ~130, `.shred`
  `"a"` ~186). If it passes, record the finding and stop.
- **2. Fix:** `Crypto/runtime/python/key_provider_local.py` creates the store
  and `.shred` sidecar via `os.open(path, flags, 0o600)` + `os.fchmod(fd,
  0o600)` and wraps with `os.fdopen`; on load, any `0o077` bit →
  raise `LocalKeyStoreInsecure(RuntimeError)` (same name/message shape as
  C++). Skip the check on Windows, as C++ does.
- **3. Unit tests (required, kept):**
  - `test_local_store_and_sidecar_are_0600` (above) — now green.
  - `test_local_loose_store_is_refused` — loose store and loose sidecar each
    raise `LocalKeyStoreInsecure`.
  - Interop: a store written by C++ is accepted by Python and the reverse
    (both `0600`) — extend `test_backends_interchangeable` /
    `test_store_format_and_restart`.
- **Golden:** regenerate `UnitTests/golden_python/` if the runtime is
  snapshotted there; review the diff is only this change.
- **Quality gate:** `test_python_quality_gate.py`.
- **Docs:** drop the "not restricted to 0600 (parity)" note from
  `Crypto/CLAUDE.md` / the Python runtime docstring.
