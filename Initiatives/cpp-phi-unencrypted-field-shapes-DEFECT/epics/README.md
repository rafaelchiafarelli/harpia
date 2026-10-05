# cpp-phi-unencrypted-field-shapes-DEFECT — epics

One epic: **`phi-field-shapes`**.

```
1-refuse-or-encrypt-decision   (planning; Rafael decides)
        │
        ▼
2-enum-and-embedded-phi        (encrypt: model + C++/Python DAOs)
        │
        ▼
3-repeated-and-map-phi         (encrypt child-table values, or refuse)
```

## Decision for Rafael (planning, before any code)

- **(a) Fail-safe now:** the generator rejects `phi` on any shape it doesn't
  encrypt (a hard front-end/Stage 8 error naming the field), then tasks 2-3
  lift the restriction shape by shape. Matches the "strictest when
  ambiguous" posture; breaks any existing schema using these shapes (none in
  the repo).
- **(b) Encrypt directly:** tasks 2-3 only; until they land the gap stays
  silent.

Recommended: (a) as task 1's deliverable, because the current behavior is
silent plaintext.

## Definition of done

- Every `phi` field shape is either encrypted at rest (C++ and Python DAOs
  agree: `enc:v1:` stored, plaintext on read, one value-free audit record per
  op) or refused at generation time — never silently clear.
- C++ ↔ Python cross-read over one `LocalKeyProvider` store for each
  encrypted shape.
- Goldens: the HarpiaTest fixture gains the shapes (new `Include/` message)
  → reviewed golden move.
- Full Docker suite + `Docker/run_pg_tests.sh` green before merging to `dev`.
