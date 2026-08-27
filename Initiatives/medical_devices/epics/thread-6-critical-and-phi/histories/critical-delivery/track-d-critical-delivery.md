# Track D — `critical` delivery-guarantee

The `critical` message-type axis and its delivery machinery, from
`harpia_sensitive_data_design_rules.md` §0 (criticality is message-type
level, never per-field, never a payload value the transport reads) and §4
(Rule 3 envelope CRC + monotonic seq; Rule 4a bounded rotating queue for
`critical` types; Rule 4b latest-value-only mailbox; Rule 5 every fallible
op returns a distinct observable outcome).

**Why this is a track and not a footnote:** the master plan assumed it was
already built. It was not — see `../../README.md`.

## Receives (must be done before this track starts)

- **F1** (Foundation) — `ComplianceContext` threaded through every stage
  (present as a `compliance=None` kwarg; nothing here branches on it yet).
- Nothing else. D.1 has no prerequisite; D.2 needs D.1; D.3 needs D.2;
  D.4 needs D.3.

## Gives (what "done" means here, consumed by whom)

- `Message.is_critical` — a message-type-level AST flag (parallel to
  `variable.is_phi`).
- `Compliance/runtime/harpia_delivery.h` — a transport-/payload-agnostic
  delivery-guarantee runtime (`Envelope`, `check_on_arrival`,
  `BoundedQueue`, `Mailbox`), copied verbatim into generated output like
  `harpia_capability_dispatch.h` / `harpia_audit_sink.h`.
- `ZmqAdapter` routing a `critical` message type's send path through the
  Rule 4a `BoundedQueue`; non-`critical` transports byte-for-byte
  unchanged.
- **Consumed by:** a future DDS wiring
  (`../../thread-5-device-interop/histories/dds-transport/track-p-dds-transport.md`
  — QoS `critical` → `RELIABLE`/`KEEP_ALL`) would copy the same runtime
  header. Track Q reads `critical event` ≈ Alert.
- **Owed elsewhere:** the `phi`-adjacent traceability note is a Track M
  task —
  `../../thread-4-platform-infra/histories/process-artifacts/tasks/critical-delivery-note.md`
  (`ComplianceReport/` is Track M's module, blocked on M.1).

## Files this track touches

- `LexicalAnalizer/LexicalAnalyzer.py`, `Message/Message.py`.
- New `Compliance/runtime/harpia_delivery.h`, `Compliance/delivery_common.py`.
- `ZmqAdapter/ZmqAdapter.py`, `ZmqAdapter/templates/`.
- `HarpiaTest/Include/file3.harpia` fixture; `UnitTests/`;
  `UnitTests/golden/` regen (D.1, D.3).

## Sessions

One file per session in `tasks/`:

- `tasks/critical-modifier.md` — D.1
- `tasks/delivery-runtime.md` — D.2
- `tasks/zmq-wiring.md` — D.3
- `tasks/send-receive-integration-test.md` — D.4

## Watch for

- The `critical` sender's API differs from the non-critical one on purpose:
  `send()`/`publish()` return `std::optional<PushOutcome>` and only
  enqueue — callers call `flush()` to transmit.
- `AuditSink` operation strings are caller-owned — this track uses
  `"queue_rotated"` / `"mailbox_overwritten"`.
- The delivery runtime is not thread-safe (caller-synchronized); the zmq
  critical sender's `BoundedQueue` has no lock.
