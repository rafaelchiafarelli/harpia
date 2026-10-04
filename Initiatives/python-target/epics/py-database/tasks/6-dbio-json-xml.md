## DB ↔ JSON/XML bulk import/export

- **Depends on:** task 2c; `py-serialization` tasks 1–2.
- **Contract:** `harpia_generated/dbio/<name>_<hash>_dbio.py`, a port of
  `DbIoAdapter`. It provides:
  - `export_json(dao) -> str` and `import_json(dao, text) -> int`, as
    newline-delimited JSON;
  - `export_xml(dao) -> str` and `import_xml(dao, text) -> int`, with a
    `<name>_list` wrapper and elements parsed via `from_xml_element`.
- **Bar:** a Python export imports into C++ and vice versa (NDJSON lines
  cross-parse-equal; XML documents byte-identical for the same rows).
- **Out of scope:** streaming/large-export tuning.
- **Tests:** round-trip export→import into an empty table; a g++-gated
  C++-export → Python-import case.
