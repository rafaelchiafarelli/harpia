## Cross-language: presence survives any writer → any reader

- **Depends on:** tasks 1-3.
- **1. Corroborate:** extend `test_db_xlang3.py`'s matrix with a
  presence check on `patient_vitals.device_note` (unset and set-to-empty
  rows) — fails until 1-3 land (any pair).
- **2. Deliverable:** test only, unless a pair still disagrees (then fix in
  the owning language's task scope).
- **3. Unit tests (kept):** SQLite + PG halves.
