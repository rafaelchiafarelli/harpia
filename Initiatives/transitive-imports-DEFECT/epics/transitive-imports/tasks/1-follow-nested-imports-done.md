## Follow imports transitively, each module once

- **Depends on:** nothing.
- **Contract:** the set of generated modules is the transitive closure of the
  root's imports, each file processed once (diamond imports dedupe by resolved
  path; an import cycle is a pre-lex error naming the cycle). Generation order
  stays deterministic (depth-first, in import order) so goldens don't churn.
- **1. Corroborate (red first):** `UnitTests/test_transitive_imports.py` —
  root → `a.harpia` → `b.harpia` (table message in each); `B`'s proto + DAO
  must be generated. Fails today. Plus a diamond and a cycle case.
- **2. Fix:** `main.py` include loop / `LexicalAnalizer/pre_lex.py`
  `getListOfHarpias()`.
- **3. Unit tests (kept):** the three cases.
- **Golden move:** none expected (`HarpiaTest` root imports directly) — any
  golden diff is a stop-and-ask.
- **Docs:** `USAGE.md` §2 / §3, `harpia.process.md` stage 0.
