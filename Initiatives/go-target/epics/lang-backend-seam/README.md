# lang-backend-seam — a real language-plugin registry, Java retrofitted onto it

**Depends on:** nothing (pure refactor of existing, shipped behavior).

Java's own docs (`GradleAdapter/CLAUDE.md`) name the exact gap this closes:
*"No `HARPIA_GEN_LANG`-style backend registry exists yet ... README §3
explicitly defers designing that seam until a second language exists."* Go is
that second language. This epic builds the registry and moves Java's
existing, unchanged pipeline behind it — **wiring only**, confirmed
explicitly with Rafael 2026-09-03: this is not an opportunity to bring Java
up to any new feature scope.

## Task order

Sequential — each depends on the previous:

```
1-registry-and-cpp-backend
        ▼
2-java-backend-retrofit
        ▼
3-main-dispatch-and-regreen
```

## Definition of done

- `main.py` no longer contains an inline `if genLang == "java":` block (nor
  gains an inline `if genLang == "go":` one later — that's the entire point).
- `golden_java/` (`UnitTests/test_golden_java.py`) is **byte-identical**
  before and after — the retrofit changes *how* the Java pipeline is
  invoked, never *what* it produces.
- `golden/` (C++) is likewise untouched.
- Full suite green in Docker (`Docker/run.sh pytest UnitTests/`) — every
  Java-target test (`test_java_*.py`) and every C++ test passes exactly as
  before.
- The registry has an obvious extension point for `go` to register into in
  `go-foundation` (epic 1) without touching `cpp`'s or `java`'s backend
  classes.

## Watch for

- `dbBackend` (the `HARPIA_DB_BACKEND` dialect selection) is resolved once in
  `main.py` **before** the language dispatch specifically so C++ and Java
  share the identical `DbBackend` object for a given run
  (`JavaDatabase/CLAUDE.md`). The new `LangBackend` dispatch must preserve
  this — `dbBackend` gets passed *into* whichever backend's `run()` is
  called, not re-resolved per backend.
- `GradleAdapter` must run **after** `copyBasicProtos` (needs
  `errorCode.proto`/`heartBeat.proto` already copied) — an ordering
  constraint from `GradleAdapter/CLAUDE.md` that must survive being moved
  behind the registry, not just work by accident of where the call happens
  to land in the new `main.py`.
- Compliance (`complianceContext`) is threaded into every Java adapter
  constructor already — same signature expectation applies through the
  registry.
