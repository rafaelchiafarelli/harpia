# Gaps not yet assigned to any track

Added 2026-08-18, cross-referencing `README.md`'s "Known gaps" (current
harpia `dev` @ `0757180`) against every track in `foundation.md` and
`session-1` through `session-4`. Everything else on that list already maps
onto an existing track (no YAML serialization → Track F; no multi-tier
RBAC → Track C; C++-only generation target → Track J). Doxygen generation
is folded into `foundation.md` (F6 + Ground Rule 6, 2026-08-23) rather
than scoped as its own track — see that file. **True crash/interrupt
recovery, originally mapped to Track I here, is now resolved — see
below, not an open gap anymore.** This one still doesn't have a home yet:

---

## Device-interop protocols considered and deferred (2026-08-21)

Not gaps against a committed scope — these came up while scoping Track P
(DDS)/Track Q (IEEE 11073 SDC) for what's now `thread-5-device-interop/`
and were deliberately **not** turned into tracks, with reasons, so a
future session doesn't re-litigate them from scratch:

- **IEEE 11073 PHD (personal/wearable devices, 11073-20601)** — the
  personal-health-device gateway pattern (glucose meter/BP cuff/pulse-ox
  talking to a phone over BLE HDP/GATT). Different actor and different
  footprint than anything Harpia currently touches: the gateway logic
  lives phone/BLE-stack-side, not in a backend/process-to-process
  library. Revisit only if a concrete integration target puts that
  gateway role inside Harpia's scope, not preemptively.
- **MQTT and OPC UA** — both real in adjacent (industrial/IoT,
  telemetry-relay) contexts, but no medical-device-specific
  interoperability standard in the ASTM F2761/IEEE 11073 family requires
  either. Adding either without a concrete target would be speculative
  transport surface, not a filled gap. Revisit if a specific downstream
  integrator's requirement names one.
- **DICOM / IHE PCD** — these are system-to-system *clinical data
  exchange* (PACS/imaging integration), not device-level IPC. Orthogonal
  to what Harpia generates today — a different layer of the stack.
- **HL7 FHIR — revised 2026-08-21, no longer deferred.** Originally
  lumped in with DICOM/IHE PCD as "orthogonal" — that was wrong. FHIR's
  RESTful convention (verbs, JSON/XML, content negotiation) is the same
  *mechanism* Stage 12 already emits; the real gap is FHIR's fixed
  resource vocabulary + terminology bindings (`Patient`, `Observation`,
  LOINC/SNOMED-coded fields), which nothing in the generator maps to
  today. This is a legitimate façade/translation track, not a
  non-fit — see Track R in the master plan and
  `thread-5-device-interop/histories/fhir-facade/track-r-fhir-facade.md` (added 2026-08-23 —
  the original `session-5-device-interop.md` never actually included
  Track R despite the master plan naming it part of this session).

If any of these get picked back up later, scope them the same way
Track P/Q were: a dedicated track with its own contract in the master
plan, not folded silently into an existing one.

---

## ZMQ CURVE Windows build-verification

This one *is* already tracked — now as its own session, Session B.4 in
`thread-2-transport-and-access/histories/zmq-lifecycle/track-b-zmq-lifecycle.md` — listed here
only so a scan of this file catches it too. `Assets/vcpkg.json`'s `zeromq`
dependency has the `curve`+`sodium` features added; the
`-DUSE_ZMQ_CURVE=ON` build path has not been exercised on a native
Windows host.
