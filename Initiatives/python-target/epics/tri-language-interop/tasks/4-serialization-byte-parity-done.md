## Serialization byte-parity across C++, Java and Python

- **Depends on:** `py-serialization` (all).
- **Contract:** one test that serializes the same populated fixture
  messages in all three languages and compares:
  - XML and YAML: C++ ≡ Python byte-for-byte (this is the
    `py-serialization` bar, re-asserted here over the whole fixture).
    Java XML is compared too; **any C++/Java difference found is reported
    as a finding (flagged to Rafael), not fixed here**. Java has no YAML.
  - JSON: cross-parse equality in all directions, with byte differences
    (float text) listed.
  - Redacted `to_string` for phi messages: C++ ≡ Python.
- **Tests:** `UnitTests/test_serialize_xlang3.py` (gated as task 1).
