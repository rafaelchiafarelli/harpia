# Only modules the root imports directly are generated — DEFECT

**Status: scoped, not started.** Reported 2026-10-31 by `mocap-contracts`
(`harpia-handoff.md` item 1, last paragraph); Rafael: a defect, not intended.

## What was found

`main.py` takes `rootFile.getListOfHarpias()` — the root's own `import`
lines — and lexes those files. Imports inside an included file are dropped
(`ImportRemover`) and never followed. Reproduced 2026-10-31: root imports
`a.harpia`, `a.harpia` imports `b.harpia`; `A` is generated, `B` is not (no
error, no warning). A consumer can't keep a stable root that imports one
aggregator module.

## Scope

One epic, **`transitive-imports`**, one task.
