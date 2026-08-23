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

## PostgreSQL on Windows — RESOLVED 2026-08-22

Was: only SQLite verified on the native-Windows generated-code path;
`soci[postgresql]` never added to either vcpkg manifest; nothing tested
against a real Postgres server from Windows. Session with native Windows
exec access closed it: `examples/consumer/vcpkg.json` now also requests
`soci[sqlite3,postgresql]` (matching `Assets/vcpkg.json`, which already had
it); `examples/consumer/CMakeLists.txt` gained a `USE_POSTGRES` option
(default OFF) that does `find_package(PostgreSQL REQUIRED)` before
`find_package(SOCI CONFIG REQUIRED)` — no hand-written alias needed here,
unlike `SOCI::SQLite3`/`SQLite3::SQLite3` (vcpkg's `libpq` port hooks
CMake's builtin `find_package(PostgreSQL)` directly via its own
`vcpkg-cmake-wrapper.cmake`). Built and linked on MSVC + vcpkg (protobuf,
grpc, soci, libpq all compiled from source), then run against a real
`postgres:16` container: `create_table`/`create`/`list`/`read` round-tripped
over a genuine `soci::postgresql` session, verified independently via
`psql` against the container. See `USAGE.md` §8/§12 and `Assets/CLAUDE.md`
for the detail. (Note: the original "Track N's parity gate can now compare
Windows-Postgres against Linux-Postgres variants" framing this gap was
scoped under is stale — `harpia_medical_master_plan.md` §0a dropped Track
N's cross-variant parity diff entirely, since there's only one code path
now, not one per jurisdiction. Windows-Postgres is simply verified,
full stop.)

---

## True crash/interrupt recovery (Track I) — RESOLVED 2026-08-19, doc drift found and fixed 2026-08-23

Was: mapped to Track I (`harpia_medical_master_plan.md`), scoped as a
dual sha256 registry + per-file `.sha256` sidecars + start/finish markers,
per the original design vision's spec text. Actually shipped
2026-08-19, via a different, simpler mechanism — **not** the registry:
every generated file already goes through
`Util.util.write_if_different`/`copy_if_different` (content comparison,
atomic same-directory temp-file + `os.replace`), which makes a killed
mid-write never leave a truncated file, and makes rerunning the whole
pipeline after a kill self-resuming for free (already-correct files
reproduce identical content and are skipped, incomplete ones get written).
No registry, no `.sha256` sidecars, no start/finish markers, no
`per-process`/`main` registry files — see `util/CLAUDE.md`.

**Found 2026-08-23, while reconciling an unrelated question about this
mechanism:** this resolution had not propagated everywhere. Three other
docs still described crash recovery as unstarted/aspirational after it
had shipped: `README.md`'s "Known gaps" (fixed — see that file's
2026-08-23 correction note), this file's own opening paragraph (fixed
above), and `harpia_medical_master_plan.md`/`session-4-platform-infra.md`
(the latter since restructured into `thread-4-platform-infra/` — see
below), which both still carried Track I's full original sha256-registry
contract as a "not started" deliverable (fixed — see the 2026-08-23
update notes on both, and `thread-4-platform-infra/README.md`'s own note
that Track I isn't represented there at all).

**Fallout from this fix — decided 2026-08-23:** Track L (versioning/git
integration) was scoped to depend on Track I — "shares registry
version-stamp fields" — because the original design had version metadata
living *in* the sha256 registry. That registry doesn't exist. Track L's
underlying feature (git fork-tracking for generated projects) is still a
genuine, unbuilt gap — confirmed nothing exists for it in the current
codebase. Resolved: folded into Track M's `ComplianceReport/`/SBOM output
instead of a new mechanism. See `harpia_medical_master_plan.md` and
`thread-4-platform-infra/histories/versioning/track-l-versioning.md`'s Track L contracts —
both now carry a real session breakdown (L.1/L.2).

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
