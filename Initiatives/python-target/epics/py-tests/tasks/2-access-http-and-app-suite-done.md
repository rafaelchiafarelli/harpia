## Generated access-rights / REST / SOAP bodies + app-level suite

- **Depends on:** task 1; `py-transports-http` (all).
- **Contract:** extend the generated tests to `TestAdapter`'s remaining
  bodies (read `TestAdapter/CLAUDE.md` first):
  - **access rights / modifiers:** flat or RBAC, chosen per message by
    `Database.auth_gate.effective_rbac(msg, hardened)` (imported). Flat
    checks the credential helpers; RBAC checks the `permitted()` matrix
    spread + `decide("", …) == UNAUTHENTICATED`.
  - **REST / SOAP:** an in-process `HttpServer` on an ephemeral port per
    test module. Flat bodies do full credentialed round-trips. RBAC bodies
    assert fail-closed (anon → 401 / 401 Fault), with substance checked via
    DAO + serializers. That is the C++ split, for the same reason: an mTLS
    identity is the job of the harness, not of per-message generated tests.
  - **app-level suite** `tests/test_app_<hash>.py`: all-good, crash,
    slower, non-parseable (C++ 14.11–14.14), on the representative message
    picked by the same rule as `TestAdapter._pick_rep`.
- **Tests:** `UnitTests/test_python_generated_tests.py` runs the full
  emitted suite under the repo's hardened profile **and** under a
  flat/low-risk profile (`test_stage14.py`'s two-profile pattern). Both
  must pass.
