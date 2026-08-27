## Session D.4 — JSON/XML adapter doc comments

- **Depends on:** F6 (shipped).
- **Expected covered by:** Track F
  (`../../../../../medical_devices/epics/thread-3-message-behavior/histories/serialization/track-f-serialization.md`),
  which lists `JsonAdapter/`, `XmlAdapter/` in its own Files-touched
  section. **Check whether Track F's sessions (F.1–F.5) already shipped
  these comments before picking this up here.**
- **Deliverable:** two doc comments, both from
  `../../../../doxygen-generation.md` §4:
  - `XmlAdapter`'s `to_xml`/`from_xml` doc comment carrying the
    `HasField`-vs-absent pitfall — a singular **message** field is only
    emitted when `HasField` is true, and getting this backwards can
    persist a phantom row via the DB adapters (source:
    `XmlAdapter/CLAUDE.md`).
  - A class-level doc comment on both `JsonAdapter` and `XmlAdapter`
    stating the crash-free contract: serializers never crash; OOM returns
    a standardized error (source: `README.md:330-332`).
- **Out of scope:** `YamlAdapter` — not built yet as of this writing; if
  it lands before this session is picked up, fold it in as a third
  target for the same two comments, and check whether Track F's own F.1
  already added the class-level one (it built `YamlAdapter` fresh).
- **Tests:**
  - Golden snapshot: `XmlAdapter`'s wrapper header `to_xml`/`from_xml`
    comment text.
  - Golden snapshot: `JsonAdapter`/`XmlAdapter` class-level comment text.
