### Session J.18 — ZMQ core (no CURVE)

- **Depends on:** J.2 merged.
- **Deliverable:** `org.zeromq:jeromq` (pure-Java ZMTP reimplementation —
  no JNI, no native library, no per-platform build) wired for PUSH/PULL/
  PUB/SUB; the origin-id scheme (`_origin_id`, `runtime_origin_id()`)
  ports as the portable algorithm it already is.
- **Out of scope:** CURVE (J.19).
- **Tests:**
  - Integration: client/server ZMQ demo, mirroring the existing C++ one.