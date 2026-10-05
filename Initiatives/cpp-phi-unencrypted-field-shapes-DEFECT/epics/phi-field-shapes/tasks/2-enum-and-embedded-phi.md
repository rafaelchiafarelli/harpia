## Encrypt phi enum fields and phi sub-fields of embedded messages

- **Depends on:** task 1.
- **1. Corroborate (red first):** the task-1 probe's enum and embedded
  cases stored `enc:v1:` by the C++ and Python DAOs — fail today.
- **2. Deliverable:** `Database/model.py` passes `is_phi` on the enum branch
  and through `_flatten`; the column type is TEXT (as scalar phi since
  cpp-phi-numeric-column-type-DEFECT); C++ `CrudlAdapter` / Python
  `PyDatabaseAdapter` already encrypt any `is_phi` column — verify the
  embed accessor path (`Column.embed`) works in both; audit names include
  the flattened column. If task 1 chose (a), lift the refusal for these two
  shapes.
- **3. Unit tests (kept):** the red test, now green; C++ ↔ Python
  cross-read of both shapes; golden move reviewed (new fixture message in
  `HarpiaTest/Include/`).
