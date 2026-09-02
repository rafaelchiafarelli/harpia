# IEEE 11073 SDC/BICEPS device-interop bindings (scoping only)

> **Epic complete (2026-08-30) — 3/3 tasks done.** Task 1
> `UnitTests/wsdiscovery_harness.py` (stdlib WS-DD 2009 probe/resolve
> client). Task 2 new `SdcAdapter/` module + `SdcAdapter/runtime/
> harpia_wsdiscovery.h` responder, per-message `<name>_sdc.h` +
> `<name>.wsdd.xml`, fixed generic `dpws:Device` type + per-project scope
> URI, `XAddrs` → the existing Stage 11 SOAP endpoint (`SoapAdapter.py` /
> `WsdlAdapter.py` untouched). Task 3 `sdc_biceps_design.md`
> (Metric/Alert/Context mapping analysis, hypothesis only — no grammar
> change). Docker: 429 passed, 4 skipped. The full BICEPS state machine /
> MDS·VMD·Channel participant model / any `SdcAdapter/` codegen past the
> WS-Discovery responder remain a follow-on epic, gated on
> `sdc_biceps_design.md`'s open questions (V1–V7).

**Explicitly scoped as a design/scoping deliverable this pass, not a full
implementation** — same posture the master plan takes with the multi-language codegen work. IEEE
11073 SDC (ISO/IEEE 11073-10700 series: BICEPS + MDPWS) is a
substantially larger semantic lift than the dds-transport epic's transport/QoS work — it
defines a whole participant/data model (MDS → VMD → Channel →
Metric/Alert/Context hierarchy), not just a wire protocol.

**Why this leans on the transport-authn epic's Stage 11 SOAP work rather than starting
cold:** MDPWS (the SDC transport binding) is SOAP-over-HTTP with
WS-Discovery for zero-config peer discovery. Harpia's generator already
emits WSDL + SOAP endpoints (`Database/SoapAdapter.py`,
`Database/WsdlAdapter.py`, Stage 11) gated by the same credential model
the transport-authn epic is hardening.

## Receives (must be done before this epic starts)

- **F1, F2** from Foundation (see `../README.md`).
- Nothing hard from the dds-transport epic. **Flag, not a dependency:** this epic's
  design work (task 2 below) benefits from the dds-transport epic's QoS/delivery-guarantee
  mapping as a worked precedent for how a new transport ties into
  `phi`/`critical` schema-level modifiers — read
  the dds-transport epic first if available, but task 1 (WS-Discovery)
  doesn't need it at all.

## Gives (what "done" means here, consumed by whom)

- A working, standalone WS-Discovery probe/resolve responder, and a
  design doc (`sdc_biceps_design.md`) covering the
  Metric/Alert/Context mapping question — **not** implementation of the
  mapping itself.
- **Consumed by:** no current epic — the full BICEPS state machine,
  MDS/VMD/Channel implementation, and any `SdcAdapter/` codegen beyond
  the WS-Discovery responder are explicitly out of scope this pass and
  become their own future epic(s) once task 2's open question is resolved.
  **Flag:** the docs don't name that follow-on epic yet — it doesn't
  exist to be a "consumer" of this one today.

## Files this epic touches

- `Database/SoapAdapter.py`, `Database/WsdlAdapter.py` — **read as
  precedent only, never modified** (planning decision 2026-08-30). The
  master plan's "leans on... rather than starting cold" framing is about
  reusing the existing SOAP surface as the discovery target, not editing
  the adapters. `SdcAdapter/` is purely additive.
- New `SdcAdapter/` (scoping only this pass, per
  `harpia_medical_master_plan.md` §2's epic table).
- `UnitTests/` — the discovery test-client harness (task 1) and both
  test suites.
- `main.py` — one new `SdcAdapter(...).Process()` call after `WsdlAdapter`.

---

## Planning status (2026-08-30)

Planned and broken into task files. Branch chain for this clone:
`… → medical_devices → epics → sdc-biceps → tasks → <task>`.

| # | Task file | Type | Depends on | Status |
|---|---|---|---|---|
| 1 | [`tasks/ws-discovery-test-harness-done.md`](tasks/ws-discovery-test-harness-done.md) | test scaffolding (pre-work) | F1 | **done** — `UnitTests/wsdiscovery_harness.py` + 10 tests; stdlib-only WS-DD 2009 probe/resolve client, `WSDiscoveryTimeout` on no answer. Docker: 427 passed, 4 skipped. |
| 2 | [`tasks/ws-discovery-responder-done.md`](tasks/ws-discovery-responder-done.md) | real code | F1, task 1 merged | **done** — new `SdcAdapter/` module + `SdcAdapter/runtime/harpia_wsdiscovery.h` (hand-written C++17 responder, tinyxml2, POSIX multicast listener); per-message `<name>_sdc.h` + `<name>.wsdd.xml`; fixed generic `dpws:Device` type + `https://harpia.dev/sdc/scope/<project>/<message>` scope, `XAddrs` → existing Stage 11 SOAP endpoint. `SoapAdapter.py`/`WsdlAdapter.py` untouched. `golden/sdc/` + `test_sdc`; `test_wsdiscovery_responder.py` (discover → open SOAP, incl. compiled `handle_datagram` assertions). Docker: 429 passed, 4 skipped. |
| 3 | [`tasks/metric-alert-context-design-doc-done.md`](tasks/metric-alert-context-design-doc-done.md) | design doc, no code | F1, F2 | **done** — `sdc_biceps_design.md`: BICEPS Metric/Alert/Context in spec-free detail, dimension-by-dimension map of the current modifier vocabulary, `event ≈ Metric` / `critical event ≈ Alert` / `Context ≈ no-grammar-yet` as a hypothesis, 7 gaps, V1–V7 validation list. No grammar change. |

**Execution order:** task 1 → task 2 sequential (same session-line —
task 2's integration test drives the task-1 harness). Task 3 is
independent of both and can run in parallel.

**Planning decisions (see task files for the full rationale):**
- The responder advertises a **fixed generic DPWS device type** + a
  **Harpia-namespaced scope URI derived from project + message name** —
  no new `.harpia` modifier this pass.
- The WS-Discovery test client is its own task (task 1), not folded into
  task 2's implementation — it needs real code and the pre-work rule
  says that becomes its own task.
- `Database/SoapAdapter.py` / `WsdlAdapter.py` stay read-only.

## Watch for

- Task 3 can run any time; tasks 1 and 2 are sequential.
- Don't let task 3 quietly turn into a grammar change or codegen work —
  its deliverable is the design doc, full stop.
- Don't let task 1 or task 2 turn into a BICEPS data-model
  implementation — that's a follow-on epic, not this pass.
