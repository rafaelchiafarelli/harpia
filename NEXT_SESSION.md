# NEXT_SESSION — sensitive-data implementation (`phi` side: the serialization epic, serialization task 4 next)

**Branch model:** one session = one branch off `dev`, named
`features/medical_devices/thread-<N>/<track-folder>/<n>-<task-name>` — see
**`Initiatives/README.md` → "How to work an `epics/` thread"**, rules 8–11
(branch & merge flow). `dev` is the integration branch; `main` is never
touched here. `origin/dev` is current through the the serialization epic merge
(`37dc487`, 2026-08-27).

## Read first (in order)

1. **`Initiatives/README.md` → "How to work an `epics/` thread — READ THIS
   FIRST"** (rules 1–11). Non-negotiable: plan docs are frozen; `track-*.md`
   is contract-only; one numbered small file per session under `tasks/`;
   the done marker is a `-done` **filename** suffix; per-session flow =
   implement → regen+review goldens → full suite green in Docker → commit
   impl → `git mv` task file `-done` (second commit) → `git merge --no-ff`
   into `dev` → `git push origin dev` → branch next off `dev`.
2. The execution-order map:
   `Initiatives/medical_devices/epics/README.md`
   and `thread-6-critical-and-phi-done/README.md`.
3. The frozen plan (do **not** edit): `medical_devices/
   sensitive-data-implementation-roadmap.md` + `harpia_medical_master_plan.md`
   §5 (per-track contracts) + `harpia_sensitive_data_design_rules.md`.
4. The code this work builds on / just added: `Database/CLAUDE.md`
   (schema / CRUDL / migration + phi encryption + audit), `Crypto/CLAUDE.md`
   (`KeyProvider` runtime + `harpia_encrypted_column.h`),
   `Compliance/CLAUDE.md` (F1 `ComplianceContext`, F3 `AuditSink`),
   `UnitTests/CLAUDE.md` (the pinned `HASH`, golden dirs, Docker gating).

## Done so far — all merged to `dev`

- **the critical-delivery epic — `critical` delivery-guarantee — COMPLETE.**
  `epics/critical-delivery/` (all tasks).
- **the key-management epic — key management — COMPLETE.** `epics/key-management/` (all tasks `-done`). `Crypto/runtime/
  harpia_key_provider{,_local,_kms}.h`: `KeyProvider` interface + envelope
  shape, `LocalKeyProvider` + fail-safe gate, per-DEK crypto-shred,
  zeroize + `AuditSink` on every key op, `KmsClient` seam + `MockKms`.
- **the schema-evolution epic — DB schema-evolution — COMPLETE (2026-08-27).**
  `epics/schema-evolution/` (schema-evolution tasks 1–3, all `-done`; merges `23acd6e` /
  `480c096` / `a31fd30`). `migrate_<table>()` now evolves repeated-scalar,
  map, and repeated-composed **child tables** (`<table>__*`), not just the
  main table: whole-child-table rename (via `renamed_from[<old>]` on the
  field), orphan child-table reap (runtime `<table>__%` diff against
  `model.child_table_names()`), and per-child column retype / add / drop.
  New `DbBackend` methods `list_tables_sql` / `rename_table` /
  `drop_table_dynamic` / `retype_rep_child_dynamic` /
  `retype_map_child_dynamic` / `evolve_rep_composed_child_dynamic`.
  Fixture: `telemetry` + `trace_row` in `HarpiaTest/Include/file3.harpia`.
- **the db-encryption epic — DB field-level encryption + audit — COMPLETE (2026-08-27).**
  `epics/db-encryption/` (db-encryption tasks 1–4, all `-done`; merges `e5a584e` /
  `896c337` / `ee12c68` / `44ceec7`).
  - `Crypto/runtime/harpia_encrypted_column.h` (new): `encrypt_field` /
    `decrypt_field{,_ll,_int,_double}` (`enc:v1:` + hex frame over the key-management epic's envelope; unrecoverable → 0/"" never a throw), `default_key_provider()`.
  - `CrudlAdapter`: a message with a `Column.is_phi` field → its DAO holds
    a `KeyProvider& kp_` **and** an `AuditSink& audit_` (both defaulted
    ctor params, so non-phi DAOs are byte-identical); create/update
    encrypt, read/list decrypt; exactly one `audit_.record("phi_<op>",
    "<table>", "<phi col names>")` per CRUDL op (value-free, Rule 5).
    `Process()` copies `harpia_encrypted_column.h` + `harpia_key_provider*.h`
    + `harpia_audit_sink.h` into `generated/cpp/crypto/`.
  - `project.harpia.yaml` at the repo root (roadmap Phase 0) — explicit
    values equal to the strictest fail-safe defaults, so no behaviour /
    golden change; F1 still isn't branched on at generation time (db-encryption task 1
    keys off `field.is_phi`, not `ComplianceContext`).
  - `ComplianceReport/` note deferred to the process-artifacts epic: `thread-4-platform-infra/
    epics/process-artifacts/tasks/phi-db-encryption-note.md`
    (process-artifacts task 1-blocked), same as the critical-delivery epic's `critical-delivery-note.md`.
  - db-encryption task 4 closed the key-management epic's two deferred integration tests (KEK-rotation is
    O(keys); backend swap needs zero DAO change).

  Baseline: **288 passed, 4 skipped** in Docker.

- **the db-segregation epic — public/private DB segregation — COMPLETE (2026-08-27).**
  `epics/db-segregation/` (db-segregation task 1 `-done`). New `Database/DbRegistryAdapter.py`
  emits **one project-wide** `generated/cpp/db/harpia_db_registry.h` — a
  `constexpr std::array<RegistryEntry>` of `{tableName, Visibility::PUBLIC|
  PRIVATE, owner_project}` for every table-bearing message (deduped by table
  name; a differing later declaration for the same name emitted as a
  `// note:` line, not silently dropped) + `harpia::db::db_access_check(
  requesting_project, target_table)` → `AccessDecision::{ALLOWED,
  DENIED_PRIVATE_CROSS_PROJECT, DENIED_UNKNOWN_TABLE}`. Owner name = new
  `ComplianceContext.project` (`project.harpia.yaml` → `project:`, default
  `"default"`, `DEFAULT_PROJECT` in `Compliance/context.py`; parsed like
  `jurisdiction` — omitted logs+defaults, present-but-bad is a hard
  `ComplianceConfigError`). Header-only / `static_assert`-usable so a second
  generated project `#include`s this project's registry and passes its own
  name. **Purely additive** — no per-message SQL/DAO/proto change; the
  golden snapshot only gains `db/harpia_db_registry.h`. Runs in `main.py`
  right after `CrudlAdapter`. Tests: `UnitTests/test_db_segregation.py`
  (structural + g++-gated access-check + two-project integration).

- **the serialization epic — `YamlAdapter/` — COMPLETE (2026-08-27).**
  `epics/serialization/` — the inline track
  file was first restructured into `tasks/1-yaml-adapter.md … 5-…` (rule 3);
  `1-yaml-adapter-done.md`. New `YamlAdapter/` mirrors `XmlAdapter/`:
  `runtime/harpia_yaml.h` (hand-written reflection walk — protobuf has no
  built-in YAML), `to_yaml()` = block style / 2-space / top-level mapping
  with no wrapper key (JSON's data model, not XML's root element), strings
  double-quoted, scalars/enums bare, `{}`/`[]` for empty message/repeated,
  presence rule identical to `harpia_xml.h`; `from_yaml()` = an indentation
  recursive descent over exactly that subset (not a general parser; `false`
  only = "matched no field", mirroring `from_xml`). Maps via `MapEntry`
  reflection. `main.py` step 10 right after `XmlAdapter`; golden `yaml/`
  (21 wrappers, runtime not snapshotted). Tests: `UnitTests/test_stage10_yaml.py`
  (compile-all + `users` write check + flat/nested/map round-trips).
  Docker: **302 passed, 4 skipped**.

- **the serialization epic — unified `toString` façade — COMPLETE (2026-08-27).**
  `2-unified-tostring-path-done.md`. New `SerializeAdapter/` — one
  `harpia::serialize::to_string(msg, Format::{JSON,XML,YAML})` /
  `from_string` over the three **unchanged** engines (protobuf JSON util,
  `harpia_xml.h`, `harpia_yaml.h`). It is a dispatch layer, so JSON/XML
  output is byte-for-byte identical to before (acceptance gate held;
  `test_json_path_is_behavior_preserving` asserts façade == `MessageToJsonString`
  == `json/<name>_json.h`). The three formats keep their own structural
  conventions — "one shared path" = one API / one dispatch point (and one
  place serialization task 3's redaction hooks), not one output shape. `main.py` step 10
  after `YamlAdapter`; golden `serialize/` (21 wrappers, runtime not
  snapshotted); no existing golden moved. `UnitTests/test_stage10_serialize.py`.
  Docker: **307 passed, 4 skipped**.

- **the serialization epic — uniform `phi` redaction — COMPLETE (2026-08-27).**
  `3-phi-redaction-done.md`. `phi` fields now render as `[REDACTED]` by
  default in JSON/XML/YAML — wired into the **one** serialization task 2 hook, so the three
  per-format engines are untouched and a no-`phi` message is byte-for-byte
  unchanged. New `SerializeAdapter/runtime/harpia_redaction.h`
  (`kPlaceholder`, `redaction_enabled()` default TRUE, `set_redaction_enabled()`
  = serialization task 4's seam, `should_redact(msg,field)`); generated
  `serialize/harpia_phi_registry.h` (constexpr `(message,field)` phi table
  from `variable.is_phi`); `harpia_serialize.h::to_string` takes a
  redaction-aware, format-parameterised reflection walk when redaction is on
  AND `detail::tree_has_phi(descriptor)` (recursive, cycle-guarded). New
  fully-`phi` fixture `lab_result` in `HarpiaTest/Include/file3.harpia`
  (four fields, string/int/float; table-less; include-md5 bumped
  `c27dd76d…`, root HASH untouched). Golden: additive only (`lab_result`
  artifacts + `harpia_phi_registry.h`; capability adverts + `telemetry`
  line-shift); no pre-existing wrapper moved. `UnitTests/test_stage10_serialize.py`
  +4. Docker: **311 passed, 4 skipped**.

## What to do next

### 1. the serialization epic — audited unredacted-output flag

`epics/serialization/tasks/4-audited-unredacted-flag.md`. Branch
`features/medical_devices/thread-3/serialization/4-audited-unredacted-flag`
off `dev`. Unredacted `toString` output only when an explicit, non-default
flag is set (`--allow-phi-print` style), and **using that flag is itself an
audited event** (Foundation F3 `AuditSink`, `Compliance/runtime/harpia_audit_sink.h`).
The seam already exists: `harpia::redaction::set_redaction_enabled(false)`
(serialization task 3). serialization task 4 wraps it so the opt-out records one `AuditSink` entry (an
operation string like `"phi_unredacted_output"`, value-free per Rule 5) —
e.g. `harpia::redaction::allow_phi_print(AuditSink&)` — and never a silent
toggle. Copy `harpia_audit_sink.h` into `generated/cpp/serialize/` (the
`Compliance.audit_common` path constant), same as the db-encryption epic/O did for their
runtimes. Then serialization task 5 (round-trip through all three formats + a one-paragraph
`ComplianceReport/` note — see `4-*`/`5-*` task files and the thread
README's per-track `ComplianceReport/` requirement).

## Conventions / gotchas

- **Full suite in Docker before every commit** (~9 min):
  `Docker/run.sh pytest -q -p no:cacheprovider`. `run.sh` is now
  non-TTY-safe (drops `-t` when there's no terminal) and picks a
  per-Dockerfile image tag + a per-clone Gradle cache volume, so it is
  safe to run from several clones at once (see `Docker/_env.sh`;
  override `HARPIA_IMAGE` / `HARPIA_GRADLE_VOLUME` if needed). Host has
  `g++` but not
  `protoc`/`pkg-config`/`cmake` — `test_stage9` / `test_stage14` /
  `test_message_versioning_wire` / `test_critical_delivery_roundtrip` fail
  on the host and pass in Docker; not regressions.
- **Golden regen:** `HARPIA_UPDATE_GOLDEN=1 .venv/bin/python -m pytest
  UnitTests/test_golden.py UnitTests/test_golden_java.py`, then review
  `git diff UnitTests/golden` — the review is the point.
- **Pinned `HASH`** (`3ac5d8b3…`) only moves if the ROOT
  `HarpiaTest/test.harpia` text changes. New `phi`/`critical` fixtures go
  in `HarpiaTest/Include/*.harpia` (moves golden *content* for touched
  messages, leaves the `HASH = "…"` pins alone). `.harpia` comments are
  lexed like code — letters/digits/spaces + `. , ( ) { } [ ] ; = < > + -
  * /` only; a `:` / `'` / `"` / `_` / backtick anywhere in a `//`
  comment hard-errors the whole file.
- **`crypto/` generated output is not golden-snapshotted** (same as
  `delivery/`) — cover copied runtime headers with a structural test
  (`test_stage8_db.py::test_a1_encryption_runtime_copied` /
  `test_a2_key_provider_backends_shipped`).
- **`AuditSink` operation strings are caller-owned.** the db-encryption epic DB uses
  `phi_create` / `phi_read` / `phi_update` / `phi_delete` / `phi_list`;
  the key-management epic keys use `key_generate` / `key_wrap` / …; `record()` structurally
  cannot carry a value (Rule 5).
- **`users` and `top_users` both map to `user_table`** in the test
  fixture (a known multi-root collision) — `migrate_users` reaps
  `top_users`'s child tables and vice-versa, consistent with the
  pre-existing main-table column-drop behaviour. Not the schema-evolution epic/K's to fix.
