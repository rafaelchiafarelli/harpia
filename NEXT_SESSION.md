# NEXT_SESSION — sensitive-data implementation (`phi` side: Track F, F.2 next)

**Branch model:** one session = one branch off `dev`, named
`features/medical_devices/thread-<N>/<track-folder>/<n>-<task-name>` — see
**`Initiatives/README.md` → "How to work an `epics/` thread"**, rules 8–11
(branch & merge flow). `dev` is the integration branch; `main` is never
touched here. `origin/dev` is current through the Track F / F.1 merge
(`2b2cdbb`, 2026-08-27).

## Read first (in order)

1. **`Initiatives/README.md` → "How to work an `epics/` thread — READ THIS
   FIRST"** (rules 1–11). Non-negotiable: plan docs are frozen; `track-*.md`
   is contract-only; one numbered small file per session under `tasks/`;
   the done marker is a `-done` **filename** suffix; per-session flow =
   implement → regen+review goldens → full suite green in Docker → commit
   impl → `git mv` task file `-done` (second commit) → `git merge --no-ff`
   into `dev` → `git push origin dev` → branch next off `dev`.
2. The execution-order map:
   `Initiatives/medical_devices/epics/thread-1-data-and-keys/README.md`
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

- **Track D — `critical` delivery-guarantee — COMPLETE.**
  `epics/thread-6-critical-and-phi-done/` (D.1–D.4).
- **Track O — key management — COMPLETE.** `epics/thread-1-data-and-keys/
  histories/key-management/` (O.1–O.5, all `-done`). `Crypto/runtime/
  harpia_key_provider{,_local,_kms}.h`: `KeyProvider` interface + envelope
  shape, `LocalKeyProvider` + fail-safe gate, per-DEK crypto-shred,
  zeroize + `AuditSink` on every key op, `KmsClient` seam + `MockKms`.
- **Track H — DB schema-evolution — COMPLETE (2026-08-27).**
  `histories/schema-evolution/` (H.1–H.3, all `-done`; merges `23acd6e` /
  `480c096` / `a31fd30`). `migrate_<table>()` now evolves repeated-scalar,
  map, and repeated-composed **child tables** (`<table>__*`), not just the
  main table: whole-child-table rename (via `renamed_from[<old>]` on the
  field), orphan child-table reap (runtime `<table>__%` diff against
  `model.child_table_names()`), and per-child column retype / add / drop.
  New `DbBackend` methods `list_tables_sql` / `rename_table` /
  `drop_table_dynamic` / `retype_rep_child_dynamic` /
  `retype_map_child_dynamic` / `evolve_rep_composed_child_dynamic`.
  Fixture: `telemetry` + `trace_row` in `HarpiaTest/Include/file3.harpia`.
- **Track A — DB field-level encryption + audit — COMPLETE (2026-08-27).**
  `histories/db-encryption/` (A.1–A.4, all `-done`; merges `e5a584e` /
  `896c337` / `ee12c68` / `44ceec7`).
  - `Crypto/runtime/harpia_encrypted_column.h` (new): `encrypt_field` /
    `decrypt_field{,_ll,_int,_double}` (`enc:v1:` + hex frame over Track
    O's envelope; unrecoverable → 0/"" never a throw), `default_key_provider()`.
  - `CrudlAdapter`: a message with a `Column.is_phi` field → its DAO holds
    a `KeyProvider& kp_` **and** an `AuditSink& audit_` (both defaulted
    ctor params, so non-phi DAOs are byte-identical); create/update
    encrypt, read/list decrypt; exactly one `audit_.record("phi_<op>",
    "<table>", "<phi col names>")` per CRUDL op (value-free, Rule 5).
    `Process()` copies `harpia_encrypted_column.h` + `harpia_key_provider*.h`
    + `harpia_audit_sink.h` into `generated/cpp/crypto/`.
  - `project.harpia.yaml` at the repo root (roadmap Phase 0) — explicit
    values equal to the strictest fail-safe defaults, so no behaviour /
    golden change; F1 still isn't branched on at generation time (A.1
    keys off `field.is_phi`, not `ComplianceContext`).
  - `ComplianceReport/` note deferred to Track M: `thread-4-platform-infra/
    histories/process-artifacts/tasks/phi-db-encryption-note.md`
    (M.1-blocked), same as Track D's `critical-delivery-note.md`.
  - A.4 closed Track O's two deferred integration tests (KEK-rotation is
    O(keys); backend swap needs zero DAO change).

  Baseline: **288 passed, 4 skipped** in Docker.

- **Track K — public/private DB segregation — COMPLETE (2026-08-27).**
  `histories/db-segregation/` (K.1 `-done`). New `Database/DbRegistryAdapter.py`
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

- **Track F / F.1 — `YamlAdapter/` — COMPLETE (2026-08-27).**
  `thread-3-message-behavior/histories/serialization/` — the inline track
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

## What to do next

### 1. Track F / F.2 — unified `toString` path across JSON/XML/YAML

`histories/serialization/tasks/2-unified-tostring-path.md`. Branch
`features/medical_devices/thread-3/serialization/2-unified-tostring-path`
off `dev`. Fold the three independent JSON/XML/YAML `toString` entry points
into one shared code path. **Acceptance gate:** existing JSON/XML golden
snapshots (`json/`, `xml/`) unchanged for non-`phi` messages — behavior-
preserving refactor. Then F.3 (uniform `phi` redaction — needs a
fully-`phi` fixture message; add it to `HarpiaTest/Include/*.harpia`, not a
new root file — see the track file's "Watch for"), F.4 (audited
`--allow-phi-print` flag), F.5 (round-trip + `ComplianceReport/` note).

## Conventions / gotchas

- **Full suite in Docker before every commit** (~9 min):
  `docker run --rm -u "$(id -u):$(id -g)" -v "$PWD":/harpia -v
  harpia-gradle-cache:/tmp/.gradle -w /harpia -e HOME=/tmp -e
  GRADLE_USER_HOME=/tmp/.gradle harpia-build pytest -q -p no:cacheprovider`.
  Do **not** use `Docker/run.sh` non-interactively. Host has `g++` but not
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
- **`AuditSink` operation strings are caller-owned.** Track A DB uses
  `phi_create` / `phi_read` / `phi_update` / `phi_delete` / `phi_list`;
  Track O keys use `key_generate` / `key_wrap` / …; `record()` structurally
  cannot carry a value (Rule 5).
- **`users` and `top_users` both map to `user_table`** in the test
  fixture (a known multi-root collision) — `migrate_users` reaps
  `top_users`'s child tables and vice-versa, consistent with the
  pre-existing main-table column-drop behaviour. Not Track H/K's to fix.
