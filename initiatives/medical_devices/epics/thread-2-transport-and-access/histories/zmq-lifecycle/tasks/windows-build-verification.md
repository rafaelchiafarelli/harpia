## Session B.4 — Windows build-verification (existing CURVE feature)

- **Depends on:** nothing from this track — this verifies the
  **already-shipped** CURVE transport, not B.1–B.3's new work. Can run
  any time, independently of the other sessions in this track.
- **Constraint, same as the resolved PostgreSQL-on-Windows gap
  (`gaps-not-yet-tracked.md`): needs native Windows exec access.** Not
  build-verified there yet — `Assets/vcpkg.json`'s `zeromq` dependency
  has the `curve`+`sodium` features added, but nothing has been built
  against them on a native Windows host.
- **Deliverable:** build and verify the CURVE-enabled ZMQ demo on native
  Windows (MSVC + vcpkg), same posture as the Postgres-on-Windows
  resolution.
- **Tests:** the build + a real CURVE-enabled client/server exchange on
  Windows *is* the test, same shape as the Postgres resolution's
  container-verified round trip.