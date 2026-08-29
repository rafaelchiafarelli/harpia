## Zeroization + `AuditSink` wiring

- **Depends on:** task 1 merged; F3's `AuditSink` stub (Foundation).
- **Deliverable:** key material cleared from memory after use, not left
  to garbage collection/deallocation timing; every key operation
  (generate, wrap, unwrap, rotate, shred) routed through `AuditSink` — key
  management is itself a security-relevant, auditable activity.
- **Guarantees:** no raw key material ever appears in source code,
  generated config, or logs in plaintext (mechanically checkable).
- **Tests:**
  - Unit: mock `AuditSink`, assert exactly one call per key-operation
    type (generate/wrap/unwrap/rotate/shred).
  - Unit/CI: grep-style scan across generated output and logs asserting
    no raw key material ever appears in plaintext.

### Landed as

- `Crypto/runtime/harpia_key_provider.h` — **zeroization:**
  `detail::secure_zero(std::string&)` (volatile-guarded in-place wipe +
  clear + `shrink_to_fit`); `Dek` became a class with a zeroizing
  destructor (+ explicit ctor and defaulted copy/move so it stays a value
  type for `std::optional<Dek>`); `InMemoryKeyProvider` zeroizes KEKs in
  `forget_kek_version()` and its destructor. `detail::random_bytes()`
  factored out (was duplicated per provider). **AuditSink:**
  `InMemoryKeyProvider`'s ctor takes a trailing defaulted
  `compliance::AuditSink&`; every op records `kOpGenerate` / `kOpWrap` /
  `kOpUnwrap` (with an `"ok"`/`"shredded"`/`"unknown_version"` detail) /
  `kOpRotate` / `kOpShred`, subject `"kek:<v>"` or `"dek"` — never key
  bytes (Rule 5, structural — `record()` has no value param).
- `Crypto/runtime/harpia_key_provider_local.h` — same `AuditSink&` ctor
  param + per-op records; KEK zeroize on eviction / in the destructor; the
  throwaway ctor-init KEK v1 is wiped in `load()` before the move-assign.
- `Crypto/key_provider_common.py` — `KEY_PROVIDER_RUNTIME_DEPS = ((AUDIT_SINK_RUNTIME, …),)`;
  the backend `_DEPS` tuples now include it transitively.
- `UnitTests/test_key_provider_audit.py` — 8 tests (1 pure-Python: no
  hardcoded key literals in the headers; 7 g++-gated). The 3 existing
  crypto test files gained `-I Compliance/runtime` for the new
  `#include "harpia_audit_sink.h"`.
- Additive — no generator code touched, no golden impact. Host 191 passed;
  full Docker suite 263 passed, 4 skipped.
