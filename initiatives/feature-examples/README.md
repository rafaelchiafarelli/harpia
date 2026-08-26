# Feature examples + shared-fixture restructuring

Motivated by a gap, not a bug: `HarpiaTest/app_example/consumer` is the only worked
example showing a user how to actually consume harpia-generated code, and
it only covers 3 of the ~10 generated features (DB CRUDL, JSON, REST) for
one message. gRPC, SOAP, XML, ZMQ, capability negotiation, and
credential-gated access are all exercised by the pytest suite but never
shown to a user as a small runnable program. Separately, the shared
`HarpiaTest/test.harpia` + `Include/*.harpia` fixture that ~40 test files
and every golden snapshot depend on carried three near-duplicate grab-bag
messages (`pope`/`king`/`queenBee`) that added no unique coverage, while
`file3.harpia` already showed the right pattern: one message per feature,
one comment explaining exactly what it exercises.

This thread does both, in lockstep so the fixture and the examples stay
driven by the same documented source of truth: (1) clean up the shared
fixture into clearly-labeled, one-feature-per-file `Include/` files, then
(2) build one small standalone example program per feature reusing those
same messages.

**Status:**

- **EX.1 (fixture restructuring) — shipped 2026-08-24** (`f247b6c`, merged
  via `a8f0a14`). `pope`/`king`/`queenBee` folded into `queen`
  (`HarpiaTest/Include/file3.harpia`); six pinned `HASH` constants bumped;
  golden snapshots regenerated + reviewed. Rationale now lives in
  `HarpiaTest/CLAUDE.md` / `tests/CLAUDE.md`, so its session write-up has
  been retired from the breakdown below.
- **EX.2–EX.8 (one example program per feature + the index) — not started.**

Session breakdown for the remaining work:
[track-ex-feature-examples.md](histories/track-ex-feature-examples.md).

---

## Two things resolved before any code was written

1. **A modifier literally named "critical" does not exist in the
   grammar.** It's a *proposed, unimplemented* concept in
   `initiatives/medical_devices/harpia_sensitive_data_design_rules.md` — a
   message-type-level QoS/delivery-guarantee tag (ordered/guaranteed
   delivery), not a per-field confidentiality tag, and not scoped as a
   track there yet. The closest thing that actually exists today and
   plausibly matches "critical variables" is the credential-gated access
   system (`X-User`/`X-Pswd` over REST/SOAP, `x-user`/`x-pswd` metadata
   over gRPC → 401/`UNAUTHENTICATED` on mismatch) — Session EX.6 builds
   that demo and documents this mapping explicitly rather than inventing
   a fictitious feature.
2. **`phi` has zero runtime effect today.** `variable.is_phi` is set on
   the front-end AST (`message/Variables.py`) and never read by anything
   downstream — the emitted `.proto` for a `phi` field is byte-identical
   to the same field without it (confirmed against `tests/CLAUDE.md`'s
   description of `test_phi_modifier.py`). A compiled C++ "phi demo"
   would have nothing real to show. Session EX.8 is a documentation note,
   not a runnable program, reusing the existing `patient_vitals` fixture
   message + `tests/run_phi_check.py`'s existing reflection output, and
   is explicit that no encryption/redaction/audit exists yet (that's
   Foundation Track A/F in `initiatives/medical_devices/`, not started).

## What the remaining work touches

- New `HarpiaTest/app_example/{grpc_demo,soap_demo,xml_demo,zmq_demo,access_demo,
  capability_demo}/` (EX.2-EX.7), each mirroring `HarpiaTest/app_example/consumer`'s
  proven shape (`-DHARPIA_GEN=<path>` CMake build, a README with an
  "expected output" block).
- `HarpiaTest/app_example/README.md` (new index, EX.8) and one root `README.md` bullet
  once everything lands.

(EX.1 also touched `HarpiaTest/Include/*.harpia`, the six pinned `HASH`
constants across `tests/test_stage{8_db,10_xml,11_soap,12_rest,13,13_zmq}.py`,
and `tests/golden*/` — all shipped.)

## Definition of done (every remaining session)

- Deliverable actually builds and runs inside `docker/run.sh` against a
  project generated from the current `HarpiaTest` fixture — compiling is
  not enough, the described output must actually happen, same bar
  `HarpiaTest/app_example/consumer/README.md` already holds itself to.
- A retrospective write-up filed under `histories/` once a session
  actually lands, same convention as every other thread in this repo —
  not written in advance of the work happening.
