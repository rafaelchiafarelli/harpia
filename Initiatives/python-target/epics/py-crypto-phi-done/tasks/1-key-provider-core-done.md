## `KeyProvider` interface, envelope shape, in-memory provider, shred, zeroize, audit

- **Depends on:** `py-foundation` (all; task 4's `AuditSink`).
- **Contract:** `harpia_runtime/crypto/key_provider.py`, a port of
  `Crypto/runtime/harpia_key_provider.h` (read `Crypto/CLAUDE.md` first).
  - `Dek` (`seal`/`open`) and `WrappedDek(kek_version, bytes)`.
  - `KeyProvider` ABC: `active_kek_version`, `generate_dek`, `wrap_dek`,
    `unwrap_dek -> Dek | None` (`None` for unknown/forgotten/shredded,
    Rule 5), `rotate`, `shred_dek`.
  - `shred_key(w)`, the `OP_*` operation strings (same values as C++
    `kOp*`), and `InMemoryKeyProvider`.
  - Every provider takes a trailing `audit_sink=default_audit_sink()` and
    records `key_<op>` with subject `kek:<v>` or `dek`, never key bytes.
  - **The cipher is the same placeholder XOR as C++**, byte for byte, so
    material sealed by one language opens in the other. The real AEAD is
    still the F5-seam binding, which neither target has.
- **Zeroization, stated honestly:** key bytes live in `bytearray`s, and
  `secure_zero()` overwrites them in place on `Dek` close/`__del__` and on
  KEK eviction. CPython can still leave copies (immutable `bytes`
  temporaries, allocator reuse). The docstring and the module `CLAUDE.md`
  say "best-effort, not a guarantee", unlike C++'s `secure_zero`. Never
  claim parity here.
- **Out of scope:** persistent providers (task 2), column framing (task 3).
- **Tests:** unit tests mirroring `test_key_provider.py`,
  `test_crypto_shred.py` and `test_key_provider_audit.py` (wrap/unwrap,
  rotate is O(keys), shred → `None` with the KEK untouched, one audit
  record per op with no key bytes in any argument, `bytearray` zeroed after
  close).
