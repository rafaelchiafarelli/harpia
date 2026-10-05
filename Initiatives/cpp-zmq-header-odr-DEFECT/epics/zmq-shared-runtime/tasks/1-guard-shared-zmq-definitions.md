## Shared ZMQ definitions are emitted once per TU

- **Depends on:** nothing.
- **Decision needed (planning):** guard macro in each header (as
  `HARPIA_ZMQ_CURVE_KEYS_DEFINED` does), or move `runtime_origin_id()` (and any
  other per-header shared code — audit the template) into one copied runtime
  header `zmq/harpia_zmq_runtime.h` that every message header includes. The
  second is cleaner; bring both to Rafael.
- **Deliverable:** per the decision; audit the template for every other
  definition that isn't message-specific.
- **Golden move:** `UnitTests/golden/zmq/` regenerated and reviewed.
- **Tests:** new `test_stage13_zmq.py` case: one TU including all generated
  `zmq/*_zmq.h` compiles, links and sends one message of two types.
  Optionally collapse `test_zmq_xlang3_multipeer.py`'s per-message C++
  binaries into one.
