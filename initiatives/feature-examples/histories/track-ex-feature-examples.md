# Track EX — Feature examples + shared-fixture restructuring

## Receives (must be done before this thread starts)

- Nothing from any other thread — independent of `multi-language-targets`
  and `medical_devices`. Only reads (does not modify) the generator
  itself; every session here works in `HarpiaTest/`, `tests/`, and new
  `examples/*` directories.

## Gives (what "done" means here, consumed by whom)

- A shared test fixture where every message documents, in one line, which
  feature it exists to exercise — consumed by every future session that
  needs to add a new golden-snapshotted message (a clear place to add it,
  not another near-duplicate grab-bag).
- One small, standalone, runnable example per generated feature —
  consumed by anyone onboarding onto harpia who needs "show me how gRPC
  actually gets consumed" without reading the pytest suite.

## Files this thread touches

- `HarpiaTest/Include/*.harpia`, `HarpiaTest/test.harpia`
- `tests/test_stage8_db.py`, `tests/test_stage10_xml.py`,
  `tests/test_stage11_soap.py`, `tests/test_stage12_rest.py`,
  `tests/test_stage13.py`, `tests/test_stage13_zmq.py` (pinned `HASH`
  constant bumps only)
- `tests/golden/`, `tests/golden_java/` (regenerated, reviewed)
- new `examples/grpc_demo/`, `examples/soap_demo/`, `examples/xml_demo/`,
  `examples/zmq_demo/`, `examples/access_demo/`, `examples/capability_demo/`
- `examples/README.md` (new), root `README.md` (one bullet, at the end)

---

## Session EX.1 — Fixture restructuring

- **Depends on:** nothing.
- **Deliverable:** fold `pope` (`Include/file1.harpia`), `king`
  (`file2.harpia`), `queenBee` (`file4.harpia`) — confirmed via grep to be
  referenced only inside committed golden snapshots, never in any test's
  assertion logic — into one well-commented file, in `file3.harpia`'s
  existing style (one message, one comment naming exactly what it
  exercises). Every `Include/` file ends up doing one clear job.
- **Tests:** bump the six pinned `HASH` constants (`tests/CLAUDE.md`
  names them); regenerate golden snapshots
  (`HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest tests/test_golden.py
  tests/test_golden_java.py`); review `git diff tests/golden
  tests/golden_java` (the point of that flag, per `tests/README.md`);
  full `docker/run.sh pytest` green.
- **Acceptance gate:** no test file's *assertion logic* changes — only
  fixture content and the six hash constants. If any test actually
  asserts on `pope`/`king`/`queenBee` by name (re-check at execution
  time, not just via the grep done during planning), stop and reconsider
  before deleting.

## Session EX.2 — gRPC example

- **Depends on:** EX.1 (fixture hash must be settled before pinning a
  README to it, same reason `examples/consumer/README.md` already flags:
  "this example is pinned to HarpiaTest's hash").
- **Deliverable:** `examples/grpc_demo/` — server + client over a real
  port (`grpc::CreateChannel`/`ServerBuilder`, not in-process), `users`
  message: `push` then `pullByID`, both with correct `x-user`/`x-pswd`
  metadata (`ClientContext::AddMetadata`). Mirrors `examples/consumer`'s
  shape: `CMakeLists.txt` takes `-DHARPIA_GEN=<path>`, links
  `${GEN}/protofiles/users_<hash>_service.grpc.pb.cc` +
  `gRPC::grpc gRPC::grpc++`.
- **Tests:** build + run inside `docker/run.sh`; README documents the
  exact expected stdout, same bar as `examples/consumer/README.md`.

## Session EX.3 — SOAP example

- **Depends on:** EX.1.
- **Deliverable:** `examples/soap_demo/` — Crow-backed SOAP server
  (`harpia::soap::register_users_soap`) + a client posting raw SOAP
  envelopes (`set`/`get`/`update`/`delete`, credential in
  `<soap:Header><credentials>`), `users` message.
- **Tests:** build + run inside `docker/run.sh`; demonstrate the 401
  Fault path (wrong credential) alongside the happy path.

## Session EX.4 — XML example

- **Depends on:** EX.1.
- **Deliverable:** `examples/xml_demo/` — `harpia::xml::to_xml`/`from_xml`
  round-trip + `<name>_xsd()` dump, reusing `shipment`/`parcel` (already
  in the restructured fixture, exercises nested + repeated embed-flatten
  — no new message needed).
- **Tests:** build + run inside `docker/run.sh`; assert the round-tripped
  value matches the original.

## Session EX.5 — ZMQ example

- **Depends on:** EX.1.
- **Deliverable:** `examples/zmq_demo/` — explicit standalone PUSH/PULL
  demo, reusing `courier` (already exists specifically for this: push-only,
  exercises the per-instance runtime origin id). README states plainly
  this is for discoverability/clarity, not a replacement for
  `Assets/server_template`/`client_template` (already a generic version
  of the same thing, copied into every generated project).
- **Tests:** build + run inside `docker/run.sh`, confirm the message
  crosses and the origin id is stamped.

## Session EX.6 — Access-modifier ("critical variables") example

- **Depends on:** EX.1, EX.2 (reuses its gRPC server for the gRPC half).
- **Deliverable:** `examples/access_demo/` — credential-gated access over
  REST (and gRPC) showing correct vs. wrong `X-User`/`X-Pswd` →
  200 vs 401/`UNAUTHENTICATED`, `users` message. README states explicitly
  this is the closest existing analog to "critical variables" and links
  `initiatives/medical_devices/harpia_sensitive_data_design_rules.md` for
  the real (unimplemented) `critical` concept, so nobody mistakes this
  demo for that future feature.
- **Tests:** build + run inside `docker/run.sh`; both the accept and
  reject paths actually exercised, not just the happy path.

## Session EX.7 — Capability-negotiation example

- **Depends on:** EX.1.
- **Deliverable:** `examples/capability_demo/` — gRPC capability
  negotiation: a real `harpia::capability::negotiate()` call against a
  server with `capabilities_service` registered, and again against a stub
  server that doesn't (legacy-peer fallback), printing both outcomes.
- **Tests:** build + run inside `docker/run.sh`; both outcomes (real
  negotiation, legacy-peer fallback) actually observed in program output.

## Session EX.8 — Documentation index (`phi`, and tying it together)

- **Depends on:** EX.1-EX.7 (indexes all of them).
- **Deliverable:** new `examples/README.md` indexing every example
  (`consumer`, `android_consumer`, and EX.2-EX.7's new ones), plus a `phi`
  section — documentation only, no compiled program — pointing at
  `patient_vitals` (already in the fixture) and `tests/run_phi_check.py`'s
  existing reflection output, explicit that no encryption/redaction/audit
  exists yet. Root `README.md` gets one bullet update once this lands.
- **Tests:** none — documentation session.
