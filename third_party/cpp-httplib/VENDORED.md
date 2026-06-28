# cpp-httplib (vendored)

- **Version:** 0.18.3
- **Source:** https://github.com/yhirose/cpp-httplib (tag `v0.18.3`)
- **License:** MIT (see LICENSE)
- **Files:** `httplib.h` (single header)

Vendored in-tree (rather than installed from the system package manager) so the
exact third-party source used by harpia's Stage 12 REST layer is tracked with the
project. Header-only; needs `-lpthread`. SSL is not enabled.

To update: replace httplib.h from a newer release tag and bump the version above.
