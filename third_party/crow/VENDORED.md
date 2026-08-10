# Crow (vendored)

- **Version:** 1.3.2
- **Source:** https://github.com/CrowCpp/Crow (release `v1.3.2`, asset `crow_all.h`)
- **License:** BSD-3-Clause (see LICENSE; the amalgamated header also bundles
  ISC/MIT-licensed portions, noted in its SPDX header)
- **Files:** `crow.h` (the upstream amalgamated single header `crow_all.h`, renamed)

Vendored in-tree (rather than installed from a package manager) so the exact
third-party source used by harpia's Stage 11 (SOAP) and Stage 12 (REST) layers is
tracked with the project. Header-only, like the cpp-httplib it replaces.

Crow requires **asio**; we use standalone asio (no Boost, no OpenSSL) vendored in
`../asio/`. Crow defines `ASIO_STANDALONE` itself, so nothing extra is needed at
the build site beyond putting both `third_party/crow` and `third_party/asio` on the
include path and linking `pthread`. `CROW_USE_BOOST` and `CROW_ENABLE_SSL` are left
unset.

**Latest upstream is v1.3.3, but that release dropped the `crow_all.h` asset**, so
v1.3.2 is the newest amalgamated header available.

To update: replace `crow.h` from a newer release's `crow_all.h`, bump the version
above, and re-check the compatible asio version in `../asio/VENDORED.md`.
