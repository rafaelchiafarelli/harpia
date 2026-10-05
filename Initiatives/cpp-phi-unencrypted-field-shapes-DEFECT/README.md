# `phi` on enum / embedded / repeated / map fields is stored in plaintext — DEFECT

**Status: scoped, not started.** Found 2026-10-05 while fixing
`cpp-phi-numeric-column-type-DEFECT` (checking every column builder in
`Database/model.py` for `is_phi`). Nothing changed yet.

## What was found

`Database/model.py` passes `is_phi` to exactly one column shape: a top-level
**scalar** field of a table message (`analyze`, the `_scalar` branch). Every
other shape a `phi` field can take loses the flag, so the generated C++ and
Python DAOs store it **in plaintext, with no `phi_*` audit record and no
warning**:

| shape | where the flag is dropped | stored as |
|---|---|---|
| `phi <enum> f;` | `analyze`, enum branch (`Column(..., kind="enum")`) | INTEGER, clear |
| `phi` sub-field of an embedded table-less message (`rec.secret`) | `_flatten` (no `is_phi`) | flattened column, clear |
| `phi repeteable <scalar> f;` | `repeated_fields` → child table `value` | child table, clear |
| `phi map<K,V> f;` | `map_fields` → child table `key`/`value` | child table, clear |

Reproduced with a probe schema (enum `grade`, embedded `rec.secret`,
`notes`, `tags`, all `phi`): neither the C++ `holder_dao` nor the Python DAO
contains any `encrypt_field` / `PhiDao`; the DAO isn't even phi-bearing.
`Database/CLAUDE.md` already says `Column.is_phi` covers "scalar/enum"
columns, so the enum case contradicts the documented contract. Java has no
phi support at all (documented scope), so it is unaffected but also not a
fix target. The HarpiaTest fixture has no such field, which is why no test
caught it.

This is a confidentiality defect: the `phi` modifier silently doesn't do
what it says for these shapes.

## Scope

One epic, **`phi-field-shapes`**. See `epics/README.md`. A planning decision
comes first (task 1).
