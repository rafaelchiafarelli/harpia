## RBAC-aware generated `<name>_test.cpp`

Scoped 2026-09-01. Follow-on to **task 4 (`rbac`)**. `TestAdapter` still emits
the flat-credential access tests (`harpia::soap::authorized_<name>`,
`X-User`/`X-Pswd`, `<credentials>` → 401/200), so a **hardened** project's own
`cmake -DHARPIA_BUILD_TESTS=ON` suite fails to compile (the flat helper no
longer exists in the RBAC variant). `test_stage14.py` is currently pinned to a
low-risk profile as a stopgap; this task removes that gap.

- **Depends on:** task 4 (`rbac`) merged into `tasks` (it is — the RBAC gate +
  `harpia_rbac.h` copied next to the transport headers the generated test
  `#include`s).
- **Deliverable:**
  - `TestAdapter/TestAdapter.py` branches its three gate-touching body builders
    (`_access_rights_body`, `_rest_body`, `_soap_body`) on
    `Crypto.backend.transport_hardening_required(self.compliance)` — the same
    predicate the transport templates use. The flat variant is **byte-identical**
    to today.
  - **Hardened variant (pinned here):** the generated test proves the RBAC gate
    is *compiled in and fail-closed*, not the full role×op matrix over the wire
    (that stays harpia's own `UnitTests/test_rbac.py` — the lightweight
    generated-test harness has no mTLS, so `crow::request::client_cert_cn` is
    always empty and the only reachable RBAC outcome is
    `unauthenticated`/401):
    - `_access_rights_body` → a direct check against the copied
      `harpia::rbac` runtime: `permitted()` matches the fixed matrix for a
      spread of `(Role, Operation)` pairs, and `decide("", <op>, "<table>")`
      is `Decision::unauthenticated`.
    - `_rest_body` / `_soap_body` → stand up the plain (non-TLS) app as today
      and assert every gated route returns **401** (REST) / a 401 SOAP Fault
      (SOAP) for a request with no client-cert identity; `return 0`. No
      flat-credential round-trip.
  - `UnitTests/test_stage14.py`: drop the low-risk pin from the `generated`
    fixture (it runs the repo's real — hardened — profile again) **and** keep
    flat-gate coverage by adding one test that regenerates under an explicit
    low-risk profile and builds+runs that generated suite green. Both gate
    variants' generated tests must compile and pass.
  - Golden regen: `UnitTests/golden/gen_tests/` (the per-message
    `<name>_<hash>_test.cpp` move to the hardened bodies, since the golden is
    generated under the repo profile).
- **Out of scope:** any change to the RBAC gate itself or `harpia_rbac.h`; the
  generated gRPC test surface (TestAdapter emits no gRPC `_test.cpp`); the ZAP
  allowlist (its own task).
- **Tests:** `test_stage14.py` as above — `test_every_generated_test_compiles_and_runs`
  and `test_ctest_target_builds_and_passes` green under the hardened profile,
  plus the new low-risk-profile build-and-run.
- **Doc-comments / docs:** the three body builders' comments rewritten for the
  two variants; `TestAdapter/CLAUDE.md` updated.
