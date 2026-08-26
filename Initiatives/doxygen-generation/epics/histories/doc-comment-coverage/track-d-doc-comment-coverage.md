# Track D — Doxygen doc-comment coverage (fallback/audit track)

## Receives (must be done before this track starts)

- **F6, shipped** (`../../../doxygen-generation.md`'s status note; see
  `../../../../medical_devices/epics/handoff-document.md`'s F6 section) —
  the Doxyfile/CMake target/mainpage machinery this track's output gets
  displayed through. Nothing else — Track D itself has no dependency on
  any in-progress medical_devices track; individual sessions below may.
- `../../../doxygen-generation.md` §4, the pitfall table, is the source of
  truth for *what* each doc-comment must say. This track file doesn't
  restate that content — it maps each row (and the templates §3 lists with
  no row yet) onto a session and a expected owner.

## Gives (what "done" means here, consumed by whom)

- Real, per-template Doxygen doc-comments landed in every consumer-facing
  header the generator emits, matching `../../../doxygen-generation.md`
  §4's content — not generic boilerplate.
- A golden-snapshot test per landed doc-comment (§6).
- `UnitTests/test_doxygen_docs.py` (F6) passing against this repo's own real
  generated headers, not just the synthetic fixture it's proven against
  today.
- **Consumed by:** no downstream medical_devices track — this closes out
  `../../../doxygen-generation.md` itself, and by extension Ground Rule 6's
  audit trail.

## Files this track touches

- `JsonAdapter/`, `XmlAdapter/`, `Database/{SqlAdapter, CrudlAdapter,
  GrpcServiceAdapter, DbIoAdapter, RestAdapter, SoapAdapter, WsdlAdapter}`,
  `ZmqAdapter`, `ProtoFile/FileCreator.py` — exactly the template-owner
  list in `../../../doxygen-generation.md` §3.

---

Sessions live in `tasks/` as separate files (one deliverable + tests each),
same convention as `thread-1-data-and-keys/histories/db-encryption/`:

- [shared-generated-file-banner.md](tasks/shared-generated-file-banner.md) — Session D.1
- [message-class-comments.md](tasks/message-class-comments.md) — Session D.2
- [field-modifier-comments.md](tasks/field-modifier-comments.md) — Session D.3
- [json-xml-adapter-comments.md](tasks/json-xml-adapter-comments.md) — Session D.4
- [database-dao-comments.md](tasks/database-dao-comments.md) — Session D.5
- [zmq-adapter-comments.md](tasks/zmq-adapter-comments.md) — Session D.6
- [closing-sweep-and-status.md](tasks/closing-sweep-and-status.md) — Session D.7

## Watch for

- D.7 depends on D.1–D.6 *or their Ground-Rule-6 equivalents landing
  inside other medical_devices tracks* — don't block D.7 waiting on a
  Track D session that another track already covered; do check that it
  actually happened before treating it as done.
- D.5's `WsdlAdapter` item has no clearly expected owner elsewhere — see
  that task file's note.
