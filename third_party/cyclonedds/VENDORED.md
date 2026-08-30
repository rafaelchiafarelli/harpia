# Eclipse Cyclone DDS (vendored)

- **Version:** 0.10.5 (git `2cdd114cbd18340c606573b4cc8dc20cc161ec5a`)
- **Source:** https://github.com/eclipse-cyclonedds/cyclonedds (tag `0.10.5`)
- **License:** EPL-2.0 OR BSD-3-Clause (dual; Eclipse Public License v2.0 or
  Eclipse Distribution License v1.0 — see `LICENSE`, `NOTICE.md`). Not
  Apache-2.0 (the dds-transport epic's task 2a scoping note said Apache-2.0
  — corrected here against the actual `LICENSE`).
- **Files:** the upstream CMake source tree, trimmed. Kept: `src/` (the C
  library — `ddsrt`, `core`, `idl`, `security`, `tools`), `cmake/`,
  `compat/`, `ports/`, `etc/`, `README.md`, `docs/` minus `docs/dev/` (the
  top `CMakeLists.txt` calls `add_subdirectory(docs)` unconditionally,
  `docs/CMakeLists.txt` installs `../README.md`, and the build references
  `docs/manual/options.md`), `LICENSE`, `NOTICE.md`, `package.xml`, the
  `*.cmake` / `*.in` packaging helpers. Dropped: `.git`, `.azure`, CI YAML
  + dotfiles, `WiX/` (Windows installer), `examples/`, `fuzz/`, `hooks/`,
  `scripts/`, `docs/dev/` (2.6 MB of developer notes + diagrams), every
  `tests/` / `xtests/` subtree (gated by `BUILD_TESTING`, `OFF` here).

## Why vendored, and how it is built

Unlike the other `third_party/` entries (sqlite / tinyxml2 / crow / asio —
amalgamations or header-only trees compiled inline by the generated
project's CMake), Cyclone DDS is a full CMake C library with no
amalgamation. It is the ASTM F2761 / OpenICE-class bedside-bus transport
for the dds-transport epic — a third selectable transport alongside gRPC
and ZMQ.

**Hybrid vendoring (decided with Rafael, 2026-08-29):** the exact source
snapshot lives here for provenance and the SBOM (`ComplianceReport/`), but
it is **built once in the Docker toolchain image** (`Docker/Dockerfile`
`COPY`s this tree and runs `cmake … && cmake --install`), the same posture
as protobuf / gRPC / ZeroMQ / SOCI — "the heavier libs, like on a board."
It is *not* pulled into every generated project's CMake as an
`add_subdirectory`. `cyclonedds-cxx` (the `ddscxx` C++ binding) is vendored
alongside in `../cyclonedds-cxx/` and built immediately after, against this
install.

Build flags used in the image: `-DBUILD_TESTING=OFF -DBUILD_EXAMPLES=OFF
-DBUILD_IDLC=ON -DENABLE_SECURITY=ON -DENABLE_SSL=ON` (the DDS-Security
plugins are OpenSSL-backed — `libssl-dev` is already in the image — so they
map onto the F5 `CryptoBackend` seam that dds-transport task 3 will wire
in).

## To update

Replace this tree from a newer `cyclonedds` release tag (headers + `src/`
+ the CMake/packaging helpers; drop the same dev/CI/test cruft as above),
bump the version + git sha above, keep `cyclonedds-cxx` on the matching
tag, and rebuild the Docker image (its per-Dockerfile hash changes, so
`Docker/run.sh` rebuilds automatically).
