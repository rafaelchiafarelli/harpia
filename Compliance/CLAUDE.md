# Compliance — project-wide compliance profile + AuditSink stub (Foundation F1/F3) + delivery-guarantee runtime (Phase 3a)

**Pipeline role:** Cross-cutting, all stages. Three independent pieces (the
third added by the sensitive-data roadmap, not Foundation):
1. **F1 — `ComplianceContext`** (`context.py`), Python, generation-time.
   Parsed once at generation start (`main.py`, mirrored in
   `UnitTests/run_pipeline.py`); threaded into every `Stage*` constructor as an
   optional `compliance=` kwarg alongside the args each already takes
   (`messages`/`dest`/etc.). See the F1 section of
   `Initiatives/medical_devices/epics/handoff-document.md` (the Foundation
   thread itself was merged to `dev` and removed; see git history for the
   original implementation write-up) and the design-rules doc §6a.
   **Plumbing only, by design:** no stage
   branches on these values yet (that starts in later tracks -- Track
   A/C/O/...); every constructor just stores `self.compliance` and ignores
   it.
2. **F3 — `AuditSink`** (`runtime/harpia_audit_sink.h`), hand-written C++,
   copied verbatim into a *generated project*'s output (like
   `Capability/runtime/harpia_capability_dispatch.h`) -- NOT a Python
   abstraction. See the F3 section of
   `Initiatives/medical_devices/epics/handoff-document.md` (the Foundation
   thread itself was merged to `dev` and removed; see git history for the
   original implementation write-up). Interface + `NoOpAuditSink` stub only, no real (tamper-evident)
   implementation yet -- that's Track A (DB) and Track C (transport)'s job,
   independently, once each starts.
3. **Phase 3a — delivery-guarantee runtime** (`runtime/harpia_delivery.h`),
   hand-written C++, transport-agnostic. The bounded rotating queue
   (design-rules Rule 4a, for `critical` message types) + single-slot
   mailbox (Rule 4b, latest-value-only) + `Envelope` (Rule 3: origin CRC +
   monotonic seq, verified only at trust boundaries) + `peek()` (a
   non-destructive look at the queue front, so a drain loop can send-then-pop
   and keep order across a failed send). Rotation/overwrite are audited
   through the F3 `AuditSink` -- never a silent drop. **Phase 3b (done):**
   `ZmqAdapter` now copies this header (+ its `harpia_audit_sink.h`
   dependency) into `generated/cpp/delivery/` and routes a `critical`
   message type's zmq sender/publisher send path through the `BoundedQueue`
   (`Message.is_critical`, roadmap Phase 1a, is the selector). The `Mailbox`
   is still unwired — Rule 4b's latest-value-only path is a later call.

**Entry points:**
- F1: `load_compliance_context(path=None)` -> `ComplianceContext`.
  `strictest_profile()` -> the fail-safe default. `ComplianceConfigError`
  (subclass of `ValueError`) is raised, never returned, for a hard-error
  case.
- F3: `harpia::compliance::AuditSink::record(operation, subject, detail="")`
  (C++, pure virtual); `harpia::compliance::NoOpAuditSink` (the only
  concrete implementation so far); `harpia::compliance::default_audit_sink()`
  (a shared instance for defaulting a generated constructor's `AuditSink&`
  parameter). `Compliance.audit_common.AUDIT_SINK_RUNTIME_SRC` (Python) is
  the path constant, mirroring `Capability.capability_common`.

## Files
- `runtime/harpia_delivery.h` — Phase 3a: `harpia::delivery`. `Envelope`
  (`stamp()` computes the CRC-32 at origin, `crc_ok()` verifies at a
  boundary; self-contained CRC, no zlib), `check_on_arrival()` →
  `Arrival{Ok,CrcMismatch,SeqGap,SeqRegressed}`, `BoundedQueue` (FIFO, fixed
  capacity, `push()` → `PushOutcome{Accepted,RotatedOldest}`, `pop()`,
  `peek()` (non-destructive front look, added Phase 3b for the zmq drain
  loop), `rotations()` count, `last_rotated_seq()`, `record("queue_rotated",
  …)` on overflow), `Mailbox` (`put()` → `PutOutcome{Stored,Overwrote}`,
  `overwrites()` count, `record("mailbox_overwritten", …)`). `#include`s its
  sibling `harpia_audit_sink.h`. NOT thread-safe (caller-synchronized, same
  as `harpia_capability_dispatch.h`). Nothing reads the schema here —
  `ZmqAdapter` (Phase 3b) reads `Message.is_critical` and wires `critical`
  → `BoundedQueue` on the send path.
- `delivery_common.py` — Phase 3a path constant `DELIVERY_RUNTIME_SRC`
  (mirrors `audit_common.py`), plus `DELIVERY_RUNTIME_DEPS` — the delivery
  header pulls in `harpia_audit_sink.h` at the same relative path, so an
  adapter copying it into output must copy both into the same directory.
  **Consumed by `ZmqAdapter` since Phase 3b** (copies into
  `generated/cpp/delivery/` when a `critical` transport message exists).
- `context.py` — F1: three closed-set `Enum`s (`RiskClass`, `Topology`,
  `PhiHandling`), `ComplianceContext` (plus `jurisdiction`, a plain list of
  strings), `strictest_profile()`, and `load_compliance_context()`.
- `audit_common.py` — F3: `AUDIT_SINK_RUNTIME`/`AUDIT_SINK_RUNTIME_SRC`
  path constants, same shape as `Capability/capability_common.py`'s. No
  adapter copies the runtime header yet (nothing consumes it -- Track A/C
  haven't started); these constants exist so whichever one does first
  doesn't hardcode a path into a sibling module.
- `runtime/harpia_audit_sink.h` — F3: `AuditSink` (pure virtual `record()`)
  + `NoOpAuditSink` + `default_audit_sink()`. Hand-written, not generated.

## Key facts / gotchas
- **Three failure modes, three different outcomes** -- don't conflate them:
  1. `project.harpia.yaml` missing entirely -> `strictest_profile()`, logged
     warning.
  2. File exists, one field omitted -> just that field defaults to its
     strictest value, logged warning; the rest of the file still applies.
  3. File exists, a field present with a value not in its enum (or
     `jurisdiction` not a list of strings) -> `ComplianceConfigError`
     (fatal, raised) -- never silently defaulted or ignored. `main.py`
     catches this one specifically and `exit(-1)`s, matching the
     pipeline's existing fatal-error convention even though the mechanism
     (raise, not return-an-`Error`) differs -- this happens before any
     stage runs, so there's no `Error`-returning stage to conform to yet.
- **Enum value sets were a genuine open design decision, not something any
  planning doc pinned down** (`risk_class`/`topology`/`phi_handling` are
  named throughout `harpia_medical_master_plan.md` and the design-rules doc,
  but no concrete value list existed anywhere before this task). Decided
  2026-08-23: `RiskClass` mirrors IEC 62304 (`class_a`/`class_b`/`class_c`,
  strictest=`class_c`, per design-rules doc §6); `Topology` is a
  deployment-exposure ladder (`standalone`/`networked`/`cloud_connected`,
  strictest=`cloud_connected`); `PhiHandling` is a project-level PHI policy
  (`none`/`opt_in`/`required`, strictest=`required`). Revisit if a later
  track (Track A/C/O, or Track M's paperwork templates) needs a value this
  set doesn't cover.
- **YAML library is PyYAML, not `ruamel.yaml`** despite `requirements.txt`
  listing the latter (a stale conda-buildout artifact, not actually
  installed or used by anything in the pipeline). PyYAML is already used
  elsewhere (`GuiAdapter/tool/generator.py`) and is what's actually
  available; added explicitly to `requirements.txt` and to the Docker image
  (`python3-yaml`) by this task, since the main pipeline now depends on it
  at import time (`main.py` -> `Compliance.context` -> `yaml`), not just a
  prototype tool.
- `jurisdiction` is genuinely inert for codegen -- validated as a list of
  strings and nothing more. No closed set: it feeds Track M's paperwork-
  template selection only (§6/§9 of the design-rules doc).
- Config path resolution: explicit `path=` arg, else
  `HARPIA_COMPLIANCE_CONFIG` env var, else `./project.harpia.yaml` (same
  override convention as `main.py`'s `HARPIA_INPUT_FILE`/`HARPIA_OUTPUT_DIR`).
- **`AuditSink.record()`'s `operation` string is deliberately NOT a closed
  enum Foundation owns.** Its vocabulary spans five+ separate downstream
  tracks (DB CRUDL ops, key operations, transport send/receive, delivery-
  queue rotation, event callbacks) that don't share files with each other
  or with Foundation -- a fixed enum would force every one of them to
  modify this Foundation-owned header just to add an operation name,
  exactly the coupling "one track = one module footprint" (Ground Rule 2)
  exists to avoid. Each track invents its own operation strings.
- **`record()`'s signature has no parameter that can carry a field's actual
  value, structurally, not by convention** -- design-rules doc Rule 5
  ("never let sensitive-value content leak into logs... enforce this by
  the logging function's signature not accepting the value at all").
  `operation`/`subject`/`detail` are identifying metadata only.
- `default_audit_sink()` is a function-local `static` (Meyers singleton) so
  a generated constructor can default its `AuditSink&` parameter without
  allocating and without static-init-order-fiasco risk across translation
  units -- same reasoning as `Database/backends/__init__.py`'s
  `_REGISTRY` singletons, just at the C++ level instead of Python.

## Touchpoints
- Called by: `main.py`, `UnitTests/run_pipeline.py` (F1). F3's
  `harpia_audit_sink.h` reaches generated output since Phase 3b — as a
  co-copy dependency of `harpia_delivery.h`, pulled in by `ZmqAdapter` for a
  `critical` transport message (`Compliance.delivery_common.DELIVERY_RUNTIME_DEPS`).
  Track A/C will also copy it directly once they start. Every `Stage*`
  constructor across the repo accepts the resulting `ComplianceContext` as an
  optional `compliance=None` kwarg (LexicalAnalizer/, Message/, ProtoFile/,
  every adapter under Database/, JsonAdapter/, XmlAdapter/, ZmqAdapter/,
  {Grpc,Http,Zmq}CapabilityAdapter/, TestAdapter/) but none of them branch on
  its values yet.
- Depends on: `logger.logger`, PyYAML (`yaml.safe_load`) for F1; C++
  standard library only (`<string>`) for F3's header;
  `<deque>`/`<optional>`/`<array>`/… + `harpia_audit_sink.h` for the Phase 3a
  delivery header. No harpia-internal dependencies otherwise -- safe to
  import from anywhere without a cycle.
- Tested by: `UnitTests/test_compliance.py` (F1), `UnitTests/test_audit_sink.py`
  (F3, g++-gated), `UnitTests/test_delivery_runtime.py` (Phase 3a, g++-gated),
  `UnitTests/test_zmq_critical_delivery.py` (Phase 3b wiring, pure Python).
