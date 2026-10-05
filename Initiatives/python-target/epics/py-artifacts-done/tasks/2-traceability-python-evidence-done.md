## Python mechanisms and evidence in the traceability matrix

- **Depends on:** task 1; epics 2, 3, 5, 6, 7, 9 (the mechanisms it
  cites).
- **Contract:** `ComplianceReport/requirements.py`'s `Req` entries gain
  Python-target `mechanism` text and `test_refs` (the `UnitTests/test_python_*.py`
  files) wherever a Python mechanism exists: phi redaction, phi encryption
  + audit, critical delivery, transport hardening, ZAP, sessions, DDS
  security.
  - `traceability.json`/`.md` rows for a python-target project carry both
    targets' evidence. Whether that is one row with two evidence lists or
    one row per target is a **decision to record**, preferring the shape
    that leaves a C++-only project's output byte-identical.
  - A Python mechanism that is weaker than C++'s is stated in the row,
    never implied equal. The main case is best-effort zeroization
    (`py-crypto-phi` task 1).
- **Tests:** extend `test_traceability.py`: python-target rows
  well-formed, every cited test file exists, the zeroization caveat is
  present, and a C++-only run is unchanged.
