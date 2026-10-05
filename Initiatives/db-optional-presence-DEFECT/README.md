# `optional` field presence is lost through the database, in every language — DEFECT

**Status: scoped, not started.** Found 2026-10-05 while fixing
java-jdbc-null-text-DEFECT (which made Java match C++/Python on NULL reads).

## What was found

An `optional` scalar (proto3 explicit presence, e.g. `patient_vitals.
device_note`, `data.j`) distinguishes "never set" from "explicitly 0 / empty".
The XML and YAML runtimes keep that distinction on purpose (`harpia_xml.h`
`has_presence()`, `Message/FieldMap.py` S4). The DAOs don't, in any language:

- **write:** an unset `optional` is bound as its default value (`0` / `""`),
  never NULL — C++ `CrudlAdapter` bind locals, Python `bind.to_db`, Java
  `JdbcBind.bind`;
- **read:** a NULL column is set to the field's default, which marks it
  *present* — C++ indicator-guarded `set_x(default)`, Python
  `setattr(default)`, Java `setField(fd, getDefaultValue())`.

So `read(create(m))` returns `has_x() == true` for a field `m` never set.
`test_py_db_bind.py` even pins "an optional set to 0 keeps presence", which is
only the write half of the contract.

## Scope

One epic, **`optional-presence`** — C++, Python, Java DAOs agree: unset
`optional` ⇄ SQL NULL ⇄ absent after read. See `epics/README.md`.
