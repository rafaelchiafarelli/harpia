## WS-Discovery probe/resolve responder

Scoped 2026-08-30. **Task 2** of the sdc-biceps epic. The one piece of real,
shipped code this epic delivers this pass — a standalone, demonstrable
WS-Discovery responder emitted alongside the existing Stage 11 SOAP endpoint.
Independent of task 3 (the mapping design doc); discovery does not need the
data-model decision settled first.

### Contract

- **Depends on:** F1 (Foundation); **task 1 (`ws-discovery-test-harness`)
  merged** — the integration test drives the responder with that harness.
- **Deliverable:**
  1. A new `SdcAdapter/` module, `Database/SoapAdapter.py`-shaped:
     `SdcAdapter(messages, dest, compliance=None)` with a `Process()` that
     iterates table-bearing messages and writes with `Util.util.write_if_different`.
     A `loadTemplate`-loaded template file for the emitted artifact(s).
  2. Emitted per generated project: a WS-Discovery responder that answers a
     multicast `Probe` with a `ProbeMatch` and a unicast `Resolve` with a
     `ResolveMatch`, advertising:
     - **Types:** a fixed generic DPWS device type (a single constant this
       task defines, e.g. `dpws:Device` — no per-message or grammar-driven
       type this pass).
     - **Scopes:** a Harpia-namespaced URI derived from the project name +
       message name (same minting discipline as the FHIR `identifier.system`
       scheme — project identifier baked in so projects can't collide).
     - **XAddrs:** the transport address of the **existing Stage 11 SOAP
       endpoint** for that message (`*_soap.h` on the Crow app) — discovery
       points at the SOAP surface that already exists, it does not stand up
       a second one.
  3. The runtime side ships as a hand-written C++ header copied into the
     generated tree the same way `Capability/runtime/harpia_capability_dispatch.h`
     is (path constant + copy step), if runtime code is needed; the static
     descriptor part is a golden-tested sidecar like the `.wsdl`.
  4. Wire `SdcAdapter(...).Process()` into `main.py` immediately after the
     `WsdlAdapter(...)` call (same `messages` / `dest` / `compliance` args).
- **Explicitly not modified:** `Database/SoapAdapter.py`, `Database/WsdlAdapter.py`
  — read for precedent only (planning decision 2026-08-30). `SdcAdapter/` is
  purely additive.
- **Out of scope:** BICEPS state machine; MDS/VMD/Channel participant model;
  any grammar change; any `SdcAdapter/` codegen beyond the WS-Discovery
  responder; MDPWS message exchange past the discovery handshake.
- **Tests:**
  - Unit: the responder answers a multicast `Probe` correctly — a probe
    whose Types/Scopes match the participant's declared values gets a
    `ProbeMatch`; a non-matching probe gets silence. `Resolve` for a known
    `EndpointReference` returns the right `XAddrs`.
  - Integration: the task-1 harness sends a live multicast `Probe`,
    discovers a Harpia-generated endpoint, reads its `XAddrs`, and opens
    the existing Stage 11 SOAP/MDPWS-compatible connection successfully.
  - Acceptance gate: `UnitTests/test_stage11_soap.py` unaffected —
    WS-Discovery is additive to the existing SOAP endpoint, not a
    replacement. No pinned `HASH` constants move.
  - `UnitTests/test_golden.py` regenerated (`HARPIA_UPDATE_GOLDEN=1`) for
    the new sidecar; diff reviewed.
- **Doxygen (Ground Rule 6):** the emitted responder header/template and any
  new runtime header carry accurate Doxygen-syntax doc-comments for what
  they emit, in this session. Add a row to
  `../../doxygen-generation/doxygen-generation.md` §4 if a new pitfall
  surfaces.

**Watch for.**

- SOAP-over-UDP is SOAP 1.2, WS-Discovery 2009 namespace — not the Stage 11
  SOAP 1.1 shape. The responder envelope is built to the WS-Discovery spec,
  not from the Stage 11 templates.
- The responder is additive and must not perturb the six pinned `HASH`
  constants (`HarpiaTest/CLAUDE.md`). It emits a new sidecar file; it does
  not edit `*_soap.h` or the `.wsdl`.
- Multicast group membership + a UDP listener is new to the generated
  runtime — the delivery/threading contract for it (who owns the socket,
  is it caller-synchronised like the rest of the runtime) is a real
  decision for this task, not an assumption. Keep it consistent with the
  "not thread-safe, caller-synchronised" contract the rest of the runtime
  holds unless there's a stated reason to diverge.
- If the responder ends up advertising a Scope or Type string derived from
  a `phi`-tagged message's data, file a one-paragraph `ComplianceReport/`
  traceability note as a **process-artifacts** task (epic README rule 6).

---
## Epic context — sdc-biceps

**Contract (this pass — scoping / design deliverable, not full implementation).**
Two concrete outputs: (a) a working, standalone WS-Discovery probe/resolve
responder emitted alongside the existing Stage 11 SOAP endpoint, and (b) a
design doc answering whether the existing access-modifier vocabulary maps onto
BICEPS's Metric/Alert/Context split or forces a new modifier. The full BICEPS
state machine, the MDS/VMD/Channel participant model, and any `SdcAdapter/`
codegen beyond the WS-Discovery responder are **out of scope this pass** and
become follow-on epic(s) once the design doc's open question is resolved.
Needs `ComplianceContext` (F1) and the `phi` field tag (F2) from Foundation.

**Files.** New `SdcAdapter/` (task 2); `UnitTests/` (tasks 1 and 2).
`Database/SoapAdapter.py` and `Database/WsdlAdapter.py` are **read as precedent
only, never modified** (decided during planning 2026-08-30).

**Decided during planning (2026-08-30).**
- The responder advertises a **fixed generic DPWS device type** and a
  **Harpia-namespaced scope URI derived from project + message name** — no
  new `.harpia` modifier this pass (keeps the "design, don't implement
  grammar" posture; pre-empts nothing in task 3's open question).
- The discovery test client is its own task (task 1), done and merged
  before task 2's integration test.

**Open question (task 3 exists to answer, not assume).** Whether `stream` /
`event[cached/not-cached]` / `pull` / `push` / `pushpull` map cleanly onto
BICEPS Metric/Alert/Context, or force a new modifier the way `phi` / `critical`
were added. The `event` ≈ Metric, `critical event` ≈ Alert, Context ≈
not-yet-in-grammar hypothesis is a **hypothesis to validate with a
domain-expert / regulatory-affairs pass** — task 3 does not lock grammar from
it (design-rules §7 discipline).

**Watch for.** Don't let task 3 turn into a grammar change or codegen work —
its deliverable is the design doc, full stop. Don't let task 1 or task 2 turn
into a BICEPS data-model implementation.
