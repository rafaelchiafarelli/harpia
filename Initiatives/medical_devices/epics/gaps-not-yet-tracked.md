# Gaps not yet assigned to any epic

Added 2026-08-18, cross-referencing `README.md`'s "Known gaps" (current
harpia `dev` @ `0757180`) against every epic in the (since-merged and
removed, see git history) Foundation epic and its first sessions.
Everything else on that list already maps onto an existing epic (no YAML
serialization → serialization; no multi-tier RBAC → transport-authn;
C++-only generation target → the multi-language codegen work). Doxygen
generation was folded into Foundation's F6 + Ground Rule 6 (2026-08-23)
rather than scoped as its own epic — see `foundation-handoff.md`. **True
crash/interrupt recovery, originally mapped to the continuable-process
work here, is now resolved — see below, not an open gap anymore.** This
one still doesn't have a home yet:

---

## Device-interop protocols considered and deferred (2026-08-21)

Not gaps against a committed scope — these came up while scoping the
dds-transport (DDS) and sdc-biceps (IEEE 11073 SDC) epics and were
deliberately **not** turned into epics, with reasons, so a future session
doesn't re-litigate them from scratch:

- **IEEE 11073 PHD (personal/wearable devices, 11073-20601)** — not to be
  confused with sdc-biceps' 11073 **SDC** (a sibling standard under the
  same 11073 umbrella, already built): PHD is the *personal-health-device*
  gateway pattern (glucose meter/BP cuff/pulse-ox talking to a phone over
  BLE HDP/GATT), a different sub-standard with a different transport (BLE,
  not SDC's service-oriented bindings) and a different fixed binary
  encoding (MDER) that nothing in Harpia's adapters can read or write.
  Different actor, too: the "manager" role is phone/BLE-stack-side, and
  Harpia has no mobile/BLE generation target at all today — this would be
  a third, disjoint pillar (new codec + new transport + new target actor),
  not an incremental adapter. Revisit only if a concrete integration
  target puts that gateway role inside Harpia's scope, not preemptively.
- **DICOM** — system-to-system *imaging* exchange (PACS, radiology
  modalities: X-Ray/MRI/CT). Its own binary encoding plus the DICOM Upper
  Layer Protocol (PDU-based association negotiation, DIMSE services like
  C-STORE/C-FIND/C-MOVE) shares no code path with anything Harpia
  generates (gRPC/REST/SOAP/ZMQ) — a real PACS server won't negotiate
  anything else, so this is a full foreign protocol stack to build from
  zero, not a facade over existing plumbing. Orthogonal to what Harpia
  generates today.

**IHE PCD — reclassified 2026-08-23, was incorrectly lumped in with
DICOM above; it isn't the same kind of gap.** IHE PCD (specifically the
DEC/PCD-01 "Communicate PCD Data" transaction) has nothing to do with
imaging — it bridges *device* data (vitals, infusion rates, ventilator
data) into the EHR, wrapping it in HL7 v2 (pipe-delimited segments:
MSH/PID/OBR/OBX) typically carried over MLLP, a trivial TCP framing —
simpler than the negotiation ZMQ/gRPC already do. That makes it a legacy-
text sibling of the fhir-facade epic's FHIR façade (same use case:
device/clinical data → EHR), not a sibling of DICOM: no new transport or
foreign binary codec needed, just a new serializer (an HL7-v2-segment
adapter, same shape as `JsonAdapter`/`XmlAdapter` but emitting
fixed-position pipe-delimited segments instead of JSON/XML) plus the same
kind of fixed-vocabulary mapping problem the fhir-facade epic already
solves for FHIR resources. Still no concrete downstream consumer named
yet, so still not an epic today — but if one is, scope it as a façade
epic alongside fhir-facade, not folded into DICOM's "different layer of
the stack" dismissal.

(HL7 FHIR was originally listed here too, then revised 2026-08-21 to "no
longer deferred" once it got its own epic — removed now that it's fully
resolved: see the fhir-facade epic.)

If any of these get picked back up later, scope them the same way
dds-transport and sdc-biceps were: a dedicated epic with its own contract
in the master plan, not folded silently into an existing one.

---

## ZMQ CURVE Windows build-verification

This one *is* already assigned — now the zmq-lifecycle epic's
`windows-build-verification` task — listed here only so a scan of this
file catches it too. `Assets/vcpkg.json`'s `zeromq` dependency has the
`curve`+`sodium` features added; the `-DUSE_ZMQ_CURVE=ON` build path has
not been exercised on a native Windows host.
