# Static/fuzz analysis CI

No cross-variant parity gate — that job was dropped entirely per
`harpia_medical_master_plan.md` §0a (one project-wide `risk_class` floor,
not per-jurisdiction builds, so there are no build variants left to
diff).

## Receives (must be done before this epic starts)

- **Nothing.** Pure tooling, safe anywhere, anytime — no dependency on
  Foundation or any other epic.

## Gives (what "done" means here, consumed by whom)

- A CERT-ruleset static analysis CI job and fuzz harnesses for the
  JSON/XML/SOAP parsers.
- **Consumed by:** every epic producing generated code, in the sense
  that this validates their output — not a "consumer" relationship the
  way the db-encryption epic consumes the key-management epic's `KeyProvider`. **Flag:** no specific
  epic is named as gated on the static-fuzz-ci epic's output; it's a CI safety net, not
  a build dependency.

## Files this epic touches

- `UnitTests/`, CI config only (per `harpia_medical_master_plan.md` §2's
  epic table).

---

## CERT-ruleset static analysis CI job

- **Depends on:** nothing.
- **Deliverable:** CERT-ruleset static analysis job (cppcheck/clang-tidy)
  on generated output.
- **Guarantees:** CI fails on new static-analysis findings above an
  agreed severity.
- **Tests:** the CI job *is* the test — "acceptance gate" is a clean (or
  explicitly triaged) run against the current codebase before the job is
  considered live.

## Fuzz harness, JSON parser

- **Depends on:** nothing.
- **Deliverable:** fuzz harness for the JSON parser.
- **Guarantees:** fuzz corpus runs N iterations with no crashes.
- **Tests:** the fuzz run itself is the test.

## Fuzz harness, XML parser

- **Depends on:** nothing.
- **Deliverable:** fuzz harness for the XML parser.
- **Guarantees:** same as task 2, for XML.
- **Tests:** the fuzz run itself is the test.

## Fuzz harness, SOAP parser

- **Depends on:** nothing.
- **Deliverable:** fuzz harness for the SOAP parser.
- **Guarantees:** same as task 2, for SOAP.
- **Tests:** the fuzz run itself is the test.

## Watch for

- All four tasks are independent of each other and of every other
  epic — genuinely pure filler work — pick up any of them whenever a
  session-line has a gap to fill.
