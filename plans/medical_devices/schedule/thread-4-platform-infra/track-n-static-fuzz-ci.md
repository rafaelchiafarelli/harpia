# Track N — Static/fuzz analysis CI

No cross-variant parity gate — that job was dropped entirely per
`harpia_medical_master_plan.md` §0a (one project-wide `risk_class` floor,
not per-jurisdiction builds, so there are no build variants left to
diff).

## Receives (must be done before this track starts)

- **Nothing.** Pure tooling, safe anywhere, anytime — no dependency on
  Foundation or any other track.

## Gives (what "done" means here, consumed by whom)

- A CERT-ruleset static analysis CI job and fuzz harnesses for the
  JSON/XML/SOAP parsers.
- **Consumed by:** every track producing generated code, in the sense
  that this validates their output — not a "consumer" relationship the
  way Track A consumes Track O's `KeyProvider`. **Flag:** no specific
  track is named as gated on Track N's output; it's a CI safety net, not
  a build dependency.

## Files this track touches

- `tests/`, CI config only (per `harpia_medical_master_plan.md` §2's
  track table).

---

## Session N.1 — CERT-ruleset static analysis CI job

- **Depends on:** nothing.
- **Deliverable:** CERT-ruleset static analysis job (cppcheck/clang-tidy)
  on generated output.
- **Guarantees:** CI fails on new static-analysis findings above an
  agreed severity.
- **Tests:** the CI job *is* the test — "acceptance gate" is a clean (or
  explicitly triaged) run against the current codebase before the job is
  considered live.

## Session N.2 — Fuzz harness, JSON parser

- **Depends on:** nothing.
- **Deliverable:** fuzz harness for the JSON parser.
- **Guarantees:** fuzz corpus runs N iterations with no crashes.
- **Tests:** the fuzz run itself is the test.

## Session N.3 — Fuzz harness, XML parser

- **Depends on:** nothing.
- **Deliverable:** fuzz harness for the XML parser.
- **Guarantees:** same as N.2, for XML.
- **Tests:** the fuzz run itself is the test.

## Session N.4 — Fuzz harness, SOAP parser

- **Depends on:** nothing.
- **Deliverable:** fuzz harness for the SOAP parser.
- **Guarantees:** same as N.2, for SOAP.
- **Tests:** the fuzz run itself is the test.

## Watch for

- All four sessions are independent of each other and of every other
  track — genuinely pure filler work, pick up any of them whenever a
  session-line has a gap to fill.
