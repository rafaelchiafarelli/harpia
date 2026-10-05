## Encrypt (or keep refusing) phi repeated / map fields

- **Depends on:** task 2.
- **Decision needed (planning):** encrypt each child-table `value` (and a
  map `key`? a key is used for lookup — encrypting it breaks the `PRIMARY
  KEY (owner, key)` uniqueness semantics), or keep refusing these shapes.
  Bring options to Rafael.
- **1. Corroborate (red first):** the task-1 probe's repeated and map
  cases stored `enc:v1:` — fail today.
- **2. Deliverable:** per the decision, in the C++ `_rep_*`/`_map_*`
  writers/readers and the Python child-table path, plus the migration's
  child-table retype (value column → TEXT).
- **3. Unit tests (kept):** red test green; C++ ↔ Python cross-read;
  migration of a legacy plaintext child table documented/tested.
