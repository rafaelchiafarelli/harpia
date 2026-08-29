## Handoff — what you're giving the other five threads

Rewritten 2026-08-23 once F1-F6 actually landed (the original version of
this file predated F1's own implementation and only stated the generic
contract each task file already promises — read this version instead; it
names real files/enums/functions so a thread pickup doesn't have to re-open
all five `*-done.md` files or the `Compliance`/`Crypto`/`Assets` `CLAUDE.md`s
just to get oriented).

### F1 — `ComplianceContext` (`Compliance/context.py`)

- `load_compliance_context(path=None) -> ComplianceContext`. Path
  resolution: explicit arg, else `HARPIA_COMPLIANCE_CONFIG` env var, else
  `./project.harpia.yaml`.
- Three closed enums, values decided during F1 (nothing pinned them before):
  `RiskClass{CLASS_A, CLASS_B, CLASS_C}` (IEC 62304, strictest=`CLASS_C`),
  `Topology{STANDALONE, NETWORKED, CLOUD_CONNECTED}` (strictest=
  `CLOUD_CONNECTED`), `PhiHandling{NONE, OPT_IN, REQUIRED}` (strictest=
  `REQUIRED`). `jurisdiction` is a plain `list[str]`, inert for codegen.
- Three distinct failure modes, don't conflate them: missing file ->
  `strictest_profile()` + logged warning; file present, one field omitted
  -> just that field defaults strict, rest of file still applies; file
  present, a field has an unrecognized value -> `ComplianceConfigError`
  (subclass of `ValueError`), **raised, never silently defaulted**.
  `main.py` catches this one specifically and `exit(-1)`s.
- Every `Stage*` constructor across the repo takes an optional
  `compliance=None` kwarg and stores it — **plumbing only, nothing branches
  on the value yet.** You are very likely the first real consumer. Don't
  reinvent config parsing or add a second place that reads
  `project.harpia.yaml`.
- No checked-in `project.harpia.yaml` exists anywhere in the repo (only
  ad-hoc ones inside `UnitTests/test_compliance.py`'s `tmp_path` fixtures) --
  every default pipeline run (including the shared `HarpiaTest` build) is
  currently exercising the *missing-file/strictest* path, not a real
  config. If your epic needs to see non-default enum values flow through
  a real generation run, you'll need to add one (repo-root-relative,
  overridable via `HARPIA_COMPLIANCE_CONFIG` if you don't want it to affect
  every other test's default run).

### F2 — `phi` field modifier

- `field.is_phi` (actually `variable.is_phi`, set in `Message/Variables.py`)
  on every parsed field. Lexer token is `PHI r'phi '` (trailing space
  required) in `LexicalAnalizer/LexicalAnalyzer.py`, same category as
  `optional`/`required`/`unique`/`repeteable` -- composes with any of them,
  in any order, including on composed-type fields. Flag only: a `phi`
  field's emitted `.proto` line is byte-identical to the same field without
  it.
- **Checked-in fixture now exists** (added this session, closing a gap this
  handoff's first version didn't know about): `HarpiaTest/Include/
  file3.harpia`'s `patient_vitals` message (`phi string patient_id`,
  `phi required float heart_rate`, plain `optional string device_note`) --
  the canonical example for the db-encryption / transport-authn / serialization / sdc-biceps epics integration tests to build
  against. Extend this message rather than adding a parallel one, to keep
  the golden-snapshot footprint from sprawling. Regenerate via
  `HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest UnitTests/test_golden.py`
  and review the diff after any change to it (editing an Include file is
  safe -- it never perturbs the six pinned `HASH` constants in `UnitTests/`,
  see `HarpiaTest/CLAUDE.md` -- but it does change golden content).
- **Gotcha that will bite you if you add more `.harpia` fixtures:**
  comments are tokenized like real code (`CommentRemover()` strips comment
  *tokens* only after the whole file is lexed), so a comment body must
  itself be lexable. Colon, apostrophe, `!`, `?`, `#`, `@`, `%`, `^`, `~`,
  backtick all hit `MISMATCH` and hard-error the *entire file*, even inside
  a `//` comment. Stick to letters/digits/`. , ( ) { } [ ] ; = < > + - * /`
  and spaces (see `LexicalAnalizer/CLAUDE.md`'s "Key facts").

### F3 — `AuditSink` (`Compliance/runtime/harpia_audit_sink.h`)

- Hand-written C++, not Python -- copied verbatim into a generated project
  the same way `Capability/runtime/harpia_capability_dispatch.h` is,
  **once some adapter actually copies it** (nothing does yet -- that's your
  job, the db-encryption or transport-authn epic, whichever starts first).
- `harpia::compliance::AuditSink::record(operation, subject, detail="")`
  (pure virtual); `NoOpAuditSink` (only concrete impl so far);
  `default_audit_sink()` (Meyers-singleton shared instance for defaulting a
  generated constructor's `AuditSink&` param).
- `operation` is a plain `std::string`, **deliberately not a closed enum**
  Foundation owns -- invent your own operation-name strings, don't send a
  PR against this header just to add one. `subject`/`detail` are
  identifying metadata only, structurally incapable of carrying a field's
  actual value (design-rules doc Rule 5) -- don't change that signature.
- `Compliance.audit_common.AUDIT_SINK_RUNTIME_SRC` is the path constant to
  copy from (mirrors `Capability.capability_common`).

### F5 — `CryptoBackend` (`Crypto/backend.py`)

- ABC (`cmake_package`, `openssl_provider`, `sbom_entry()`); two stub
  backends so far, `StandardOpenSSLBackend`/`FipsOpenSSLBackend` (name +
  metadata only -- no real crypto operations exist anywhere in this repo
  yet). `get_backend()` is a `_REGISTRY`-backed singleton resolver, same
  shape as `Database.backends.get_backend` -- **call this, don't
  independently pick/link a crypto module.** Whichever of the key-management / transport-authn epics
  calls it first and second get the identical singleton object.
- Selection order: explicit name (`HARPIA_CRYPTO_BACKEND` env var) wins
  outright; else `risk_class == CLASS_C` or `topology == CLOUD_CONNECTED`
  -> FIPS backend; else plain `"openssl"`.
- `write_build_metadata()` persists the choice to `<dest>/build_metadata/
  crypto_backend.json` (write-if-different). Nothing reads it back yet --
  the process-artifacts epic's SBOM will, once it exists.

### F4 — Regression baseline

- **No lasting artifact, and that's intentional** -- a done-marker file was
  added then deliberately removed (see `2e5b967`/`4813797` in git history)
  because F4 is the standing acceptance gate, not a deliverable.
  `UnitTests/test_golden.py` + `UnitTests/golden/` *is* F4. Diff your epic's
  acceptance tests against this, not against an arbitrary earlier commit.

### F6 — Doxygen infrastructure

- `Assets/Doxyfile` + a `find_package(Doxygen QUIET)`-gated
  `add_custom_target(doxygen ...)` in `Assets/CMakeLists.txt`, copied into
  every generated project by `Util.util.copyDoxygenFiles`.
  `Doxygen/mainpage.py` assembles `USAGE_EXCERPT.md` (the
  `USE_MDFILE_AS_MAINPAGE` target) from `USAGE.md` §4/§6/§11 **at
  generation time**, not a static hand-copied duplicate -- it can't drift
  out of sync with `USAGE.md`. `doxygen` is installed in the Dockerfile so
  the gated tests actually run in CI, not just skip.
- **Ground Rule 6 is now mechanically enforced, not just written
  convention:** a gated test (`UnitTests/test_doxygen_docs.py`) asserts zero
  Doxygen warnings with `WARN_IF_UNDOCUMENTED = YES`. Today it's proven
  only against a synthetic fixture (no generated template anywhere in the
  repo uses real `///`/`/** */` comments yet -- they're plain `//` prose,
  which is Ground Rule 6's ongoing job, not F6's). **If your epic's
  generated templates don't carry real Doxygen-syntax doc-comments for
  whatever they emit, this test is where that gap will eventually surface
  once someone points it at a real generated tree.**

### Cross-cutting things every thread should know before starting

- **A pre-existing, unrelated build gap will block some of your tests in
  Docker:** `third_party/asio` is missing `asio/detail/bind_handler.hpp`,
  so anything that `#include`s `crow.h` fails to compile. Confirmed
  pre-existing (via `git stash` against a clean checkout) and not caused by
  Foundation or message-versioning. Currently red: `test_stage11_soap.py`,
  `test_stage12_rest.py`, `test_consumer_example.py`, `test_stage14.py`,
  and two Crow-server cases in `test_message_versioning_capability_http.py`
  -- see `NEXT_SESSION.md`. If your epic's tests hit this, it's not your
  regression; don't spend time chasing it as one.
- **Foundation is plumbing everywhere, functionality nowhere.** `risk_class`
  gates nothing, `phi` encrypts/redacts nothing, `AuditSink` audits nothing
  real, `CryptoBackend` links no real crypto module. You are the first
  epic to make any of these seams *do* something -- there's no prior
  branch-on-these-values code to pattern-match against, only the seam
  itself.
- **One code path, not one per jurisdiction.** `risk_class` is a single
  project-wide hardening floor (§0a of the master plan) -- never build a
  per-jurisdiction variant of anything on top of these seams.

Every epic under `epics/` builds on the seams described above; point them
at the commit that merged Foundation into `dev`.
