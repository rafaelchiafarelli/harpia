## DDS interop: C++ ↔ Python (the two DDS-capable targets)

- **Depends on:** `py-dds` (all).
- **Contract:** a full-fixture DDS scenario:
  - C++ publishers to Python subscribers and the reverse, for every `dds`
    message;
  - both QoS profiles behave the same across languages (critical survives a
    reader gap; non-critical collapses);
  - secured participants of both languages interoperate, and an
    unauthenticated peer of either language receives nothing.

  Java has no DDS (not in its scope); that is stated in the test
  docstring.
- **Tests:** `UnitTests/test_dds_xlang.py`, gated on CycloneDDS + g++ +
  the Python toolchain.
