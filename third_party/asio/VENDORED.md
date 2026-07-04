# asio (standalone, vendored)

- **Version:** 1.30.2
- **Source:** https://github.com/chriskohlhoff/asio (tag `asio-1-30-2`), the
  `asio/include/` header tree only
- **License:** Boost Software License 1.0 (see LICENSE)
- **Files:** `asio.hpp` + the `asio/` header tree (`*.hpp` / `*.ipp`, header-only)

Standalone asio (no Boost) — the transport library Crow (see `../crow/`) is built
on. Vendored in-tree so every harpia-generated project is self-contained and
cross-compilable on any board without an `libasio-dev` system package.

Used in **standalone** mode: asio auto-selects standalone for C++11+, and Crow
also defines `ASIO_STANDALONE` explicitly. No Boost, no OpenSSL. Needs `-lpthread`.

**Version choice:** pinned to 1.30.2 (rather than the newest 1.38) deliberately —
it is conservative on the required C++ standard and compiler, which matters because
harpia output is built across many different target boards/toolchains. Bump only
after confirming the newer asio still builds Crow 1.3.2 on the oldest supported
toolchain.

To update: replace `asio.hpp` + `asio/` from a newer tag's `asio/include/` tree
(headers only — drop `Makefile.am` and other build cruft) and bump the version.
