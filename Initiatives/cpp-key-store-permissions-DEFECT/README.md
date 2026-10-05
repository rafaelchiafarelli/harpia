# LocalKeyProvider KEK store is world-readable — DEFECT

**Status: scoped, not started.** Found 2026-10-04 while porting the key
providers to Python (python-target `py-crypto-phi/2`; decisions log item 24 in
`Initiatives/python-target/NEXT_SESSION.md`). Neither language was changed:
the Python port copies the C++ behavior for parity.

## What was found

`Crypto/runtime/harpia_key_provider_local.h` writes the KEK store with a plain
`std::ofstream out(path_, std::ios::trunc)` (~line 206) and the `.shred`
sidecar with `std::ofstream(..., std::ios::app)` (~line 157). The file mode is
whatever the umask gives: under the usual `022` the store holding **KEK
material** is `0644`, readable by every local user. The Python port
(`Crypto/runtime/python/key_provider_local.py`, `open(self._path, "w")` ~line
130, `.shred` ~line 186) does the same.

The local provider is the documented no-KMS fallback, so this is the default
key store of every deployment that hasn't wired a KMS.

## Scope

One epic: **`key-store-permissions`**. Runtime headers only: **no golden
move** (the runtimes are copied, not snapshotted, except where a golden copies
them verbatim — check `golden_python/harpia_runtime/crypto/` and regenerate if
present). See `epics/README.md`.
