# tinyxml2 (vendored)

- **Version:** 10.0.0
- **Source:** https://github.com/leethomason/tinyxml2 (tag `10.0.0`)
- **License:** zlib (see LICENSE.txt)
- **Files:** `tinyxml2.h`, `tinyxml2.cpp`

Vendored in-tree (rather than installed from the system package manager) so the
exact third-party source used by harpia's Stage 10 XML adapter is tracked with
the project. The generated project's CMake compiles `tinyxml2.cpp` directly.

To update: replace the two files from a new release tag and bump the version
above.
