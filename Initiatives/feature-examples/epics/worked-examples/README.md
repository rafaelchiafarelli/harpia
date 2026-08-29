# the worked-examples epic — Feature examples + shared-fixture restructuring

## Receives (must be done before this epic starts)

- Nothing from any other epic — independent of `multi-language-targets`
  and `medical_devices`. Only reads (does not modify) the generator
  itself; every session here works in `HarpiaTest/`, `UnitTests/`, and new
  `HarpiaTest/app_example/*` directories.

## Gives (what "done" means here, consumed by whom)

- A shared test fixture where every message documents, in one line, which
  feature it exists to exercise — consumed by every future session that
  needs to add a new golden-snapshotted message (a clear place to add it,
  not another near-duplicate grab-bag).
- One small, standalone, runnable example per generated feature —
  consumed by anyone onboarding onto harpia who needs "show me how gRPC
  actually gets consumed" without reading the pytest suite.

## Files this epic touches

- `HarpiaTest/Include/*.harpia`, `HarpiaTest/test.harpia`
- `UnitTests/test_stage8_db.py`, `UnitTests/test_stage10_xml.py`,
  `UnitTests/test_stage11_soap.py`, `UnitTests/test_stage12_rest.py`,
  `UnitTests/test_stage13.py`, `UnitTests/test_stage13_zmq.py` (pinned `HASH`
  constant bumps only)
- `UnitTests/golden/`, `UnitTests/golden_java/` (regenerated, reviewed)
- new `HarpiaTest/app_example/grpc_demo/`, `HarpiaTest/app_example/soap_demo/`, `HarpiaTest/app_example/xml_demo/`,
  `HarpiaTest/app_example/zmq_demo/`, `HarpiaTest/app_example/access_demo/`, `HarpiaTest/app_example/capability_demo/`
- `HarpiaTest/app_example/README.md` (new), root `README.md` (one bullet, at the end)

---

> **task 1 (Fixture restructuring) — shipped 2026-08-24**, retired from
> this breakdown. `pope`/`king`/`queenBee` (`Include/file1/file2/file4.harpia`)
> were folded into `queen` (`file3.harpia`); the six pinned `HASH` constants
> were bumped and golden snapshots regenerated + reviewed. Commit `f247b6c`
> (merged via `a8f0a14`); rationale lives in `HarpiaTest/CLAUDE.md` /
> `UnitTests/CLAUDE.md`. "The restructured fixture" the sessions below depend on
> is that shipped state.

