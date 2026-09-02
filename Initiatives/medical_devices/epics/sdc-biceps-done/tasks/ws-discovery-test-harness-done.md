## WS-Discovery test-client harness

Scoped 2026-08-30. **Task 1** of the sdc-biceps epic — split out of
`ws-discovery-responder` during planning because the responder's integration
test needs "a generic SDC-aware client or a minimal test harness mimicking
one," and a WS-Discovery client is real code that may be more than a
throwaway helper (skill rule: pre-work needing code / possibly >1 session
becomes its own task). Task 2's integration test is blocked on this task.

### Contract

- **Depends on:** F1 (Foundation). Nothing else — the harness is standalone
  test scaffolding, not library or runtime code.
- **Deliverable:** a minimal WS-Discovery client helper under `UnitTests/`
  (a plain helper module, e.g. `UnitTests/wsdiscovery_harness.py`, **not a
  test file itself**):
  1. Sends a WS-Discovery `Probe` SOAP-over-UDP envelope to the standard
     multicast group `239.255.255.250:3702`, with a caller-supplied Types
     / Scopes match.
  2. Parses the returned `ProbeMatch(es)` — extracts `EndpointReference`,
     `Types`, `Scopes`, and `XAddrs` (the transport addresses the matched
     service listens on).
  3. Can issue a follow-up unicast `Resolve` for an `EndpointReference`
     and parse the `ResolveMatch`.
  4. Returns parsed results as plain Python structures the task-2 test can
     assert on; raises a clear timeout error when nothing answers.
- **Implementation constraints:**
  - Python stdlib `socket` (UDP multicast) + an XML parser already in the
    test dependency set (`xml.etree` or the `lxml`/`tinyxml2` path the
    existing SOAP tests already use). **No new third-party dependency.**
  - No `.harpia` grammar changes, no generator changes, no runtime C++ —
    this task touches `UnitTests/` only.
- **Out of scope:** the responder itself (task 2); any BICEPS / MDPWS
  message exchange beyond the discovery handshake; a full DPWS client
  stack.
- **Tests:**
  - Unit (`UnitTests/test_wsdiscovery_harness.py`): the harness round-trips
    against a canned `ProbeMatch` / `ResolveMatch` XML fixture (feed it a
    recorded response, assert the parsed structure) — the harness itself is
    covered before task 2 leans on it.
  - Unit: a probe that no one answers raises the timeout error rather than
    hanging or returning an empty success.
- **Acceptance gate:** full Docker regression baseline still green — this
  task adds files, changes no existing behaviour.

**Watch for.**

- SOAP-over-UDP envelopes are SOAP 1.2 (`application/soap+xml`), namespaced
  `http://docs.oasis-open.org/ws-dd/ns/discovery/2009/01` — not the SOAP
  1.1 document/literal shape `Database/SoapAdapter.py` emits for Stage 11.
  Build the envelope by hand from the WS-Discovery spec, don't assume the
  Stage 11 helpers apply.
- Multicast in CI: bind and join the group on the loopback interface for
  the fixture-driven unit tests so they don't depend on the Docker
  network. The live multicast round-trip belongs to task 2's integration
  test, not here.
- If parsing / multicast socket handling grows past one session, stop and
  split again rather than absorbing it — same rule that created this task.

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
