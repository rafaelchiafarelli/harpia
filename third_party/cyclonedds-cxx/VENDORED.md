# Eclipse Cyclone DDS — C++ binding `ddscxx` (vendored)

- **Version:** 0.10.5 (git `50984cfc9a92d1ae1903d7b1479a110c77fba240`)
- **Source:** https://github.com/eclipse-cyclonedds/cyclonedds-cxx (tag `0.10.5`)
- **License:** EPL-2.0 OR BSD-3-Clause (dual — see `LICENSE`).
- **Files:** the upstream CMake source tree, trimmed. Kept: `src/`
  (`ddscxx` — the ISO C++ DDS API — and `idlcxx` — the IDL→C++ codegen
  plugin for Cyclone's `idlc`), `cmake/`, `features.hpp.in`, `README.md`,
  `docs/` (64 KB; the top `CMakeLists.txt` calls `add_subdirectory(docs)`
  unconditionally and `docs/CMakeLists.txt` installs `../README.md`),
  `LICENSE`, the `*.cmake` / `*.in` packaging helpers. Dropped: `.git`,
  `.azure`, CI YAML + dotfiles, `WiX/`, `examples/`, every `tests/` subtree.

## Relationship to `../cyclonedds/`

`ddscxx` is a separate upstream repository that layers the ISO/IEC C++
DDS API over the Cyclone DDS C core in `../cyclonedds/`. It must be built
**after** the core is built and installed — `find_package(CycloneDDS)` has
to resolve first. Kept on the exact matching release tag (`0.10.5`).

See `../cyclonedds/VENDORED.md` for the full rationale: hybrid vendoring
(source snapshot here for provenance + SBOM, built once in the Docker
toolchain image, not pulled into every generated project's CMake).

## To update

Bump in lockstep with `../cyclonedds/` — same release tag, same trim,
rebuild the Docker image.
