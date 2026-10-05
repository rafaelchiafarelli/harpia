## Shared ZMQ definitions are emitted once per TU

- **Depends on:** nothing.
- **Decision (Rafael, 2026-10-05):** guard macro, the same single-definition
  pattern as `HARPIA_ZMQ_CURVE_KEYS_DEFINED` / `HARPIA_ZMQ_STREAM_DEFINED`.
  No new shared runtime header.
- **1. Corroborate (red first):** add
  `UnitTests/test_stage13_zmq.py::test_all_zmq_headers_in_one_tu` — generate
  the fixture, write one `.cpp` that `#include`s every generated
  `zmq/*_zmq.h`, compile it. Must **fail** on unmodified code with
  *redefinition of `runtime_origin_id()`*. If it compiles, record the finding
  and stop.
- **2. Fix:** `ZmqAdapter/templates/header.h.tmpl` wraps
  `runtime_origin_id()` (~line 58) in `#ifndef HARPIA_ZMQ_ORIGIN_ID_DEFINED` /
  `#define` / `#endif`. Audit the rest of the template and
  `ZmqAdapter/ZmqAdapter.py` for any other non-message-specific definition
  emitted unguarded (CURVE and STREAM are already guarded); guard each with
  its own macro, or flag it if it isn't a pure duplicate.
- **3. Unit tests (required, kept):**
  - `test_all_zmq_headers_in_one_tu` (above) — now compiles, links, and the
    binary sends + receives one message of each of two different types over
    `inproc://`.
  - Existing `test_zmq_manytoone_runtime_origin_id` stays green (ids still
    unique).
  - Optional: collapse `test_zmq_xlang3_multipeer.py`'s per-message C++
    binaries into one (removes the workaround); only if it stays a small
    diff.
- **Golden move:** `UnitTests/golden/zmq/`; diff is only the added guards.
- **Docs:** `ZmqAdapter/CLAUDE.md` — list of guarded shared definitions.
