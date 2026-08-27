## Session O.4 — Zeroization + `AuditSink` wiring

- **Depends on:** O.1 merged; F3's `AuditSink` stub (Foundation).
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

**O.1 note:** O.1 deliberately left `AuditSink` out of `KeyProvider`'s
signature. If O.4 adds it as an `#include "harpia_audit_sink.h"` in
`harpia_key_provider.h`, add a `KEY_PROVIDER_RUNTIME_DEPS` co-copy tuple to
`Crypto/key_provider_common.py` (same shape as
`Compliance/delivery_common.py`'s `DELIVERY_RUNTIME_DEPS`).
