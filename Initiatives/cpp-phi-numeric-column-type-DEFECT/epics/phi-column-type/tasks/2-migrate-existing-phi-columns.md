## Existing databases: generated migration retypes phi columns to TEXT

- **Depends on:** task 1.
- **Deliverable:** confirm the generated C++/Python migration
  (`migrate_<name>`) sees the numeric → TEXT difference and retypes it (it
  already retypes on type mismatch — verify the CAST of existing *plaintext*
  numeric rows is acceptable, or that such rows can't exist because the DAO
  always wrote ciphertext). Document the outcome; code only if the retype
  path doesn't fire.
- **Tests:** a hand-built "older" `patient_vitals_table` with `heart_rate
  REAL` migrated by C++ and by Python (SQLite + opt-in PG) ends TEXT, rows
  still decrypt.
