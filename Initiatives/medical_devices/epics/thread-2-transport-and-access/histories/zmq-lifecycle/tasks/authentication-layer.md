## Session B.3 — ZAP authentication layer (conditional)

- **Depends on:** B.1 merged. **Decide before building:** only needed if
  this compliance context requires authenticated ZMQ (rejecting a client
  whose key isn't recognized, not just any client with valid CURVE
  crypto) — not a default part of every deployment. Confirm the
  requirement before starting this session rather than assuming CURVE
  alone is insufficient.
- **Deliverable:** a ZAP handler on top of the existing CURVE transport,
  enforcing a client-key allowlist.
- **Tests:**
  - Unit: ZAP handler rejects a client whose key isn't on the allowlist,
    even with valid CURVE crypto.