## Python components in the CycloneDX SBOM

- **Depends on:** every epic whose runtime dependencies it lists (do late).
  At minimum 1, 5, 6, 9.
- **Contract:** when the `python` backend ran, `ComplianceReport`'s
  `bom.json` additionally lists the generated Python package's runtime
  dependencies as `components[]`: `protobuf`, `grpcio`, `pyzmq`, `psycopg`
  (optional extra), `cyclonedds`.
  - Each is **declared** in `ComplianceReport/components.py` (the "declare,
    don't infer" rule), not scraped from `pyproject.toml`.
  - Version resolution: the declared pin/range from the python backend's
    single source of truth (the same constants that render
    `pyproject.toml`), or `"unknown"`. Never dropped.
  - `purl` = `pkg:pypi/<name>@<version>` when the version is known.
  - The generated Python project itself becomes a component (or a
    `metadata.component` sub-entry; **decide and record**, keeping the
    C++-only `bom.json` byte-identical).
  - **No C++-only project changes:** a run without the python backend
    produces today's `bom.json` exactly.
- **Out of scope:** listing Java's Gradle dependencies (a pre-existing gap;
  mention it in `ComplianceReport/CLAUDE.md` rather than fix it here).
- **Tests:** extend `test_sbom_emission.py` with a python-target run:
  components present, schema-valid against the vendored CycloneDX 1.5
  schema, `purl` form, and a C++-only run unchanged (golden).
