# TestProject — design notes / requirements sketch (not wired into the pipeline)

**Role:** A planning/seed folder capturing the intended feature scope for future harpia-generated projects. It is documentation and stubs, not part of the running generator or test suite.

## Contents
- `Requisits.md` — the real content: a feature checklist for what a full harpia project should cover — gRPC (call/wait, fire-and-forget, timeout), ORM, RESTful CRUD verbs, SOAP, CRUDL, multi-project (two `.harpia` files exchanging data), multi-language (C++ and Java), multi-thread. States its purpose is "a seed for future implementations."
- `Example.md` — a worked domain example ("Health Systems Inc" patient-to-administration flow) illustrating a use case.
- `CMakeLists.txt` — a stub: a single comment about generating proto/protobuf and compiling the sample; no actual targets.
- `src/main.cpp` — empty/placeholder.

## Key facts / gotchas
- Nothing here is consumed by `main.py`, `Util/`, or `tests/`. The default pipeline input is `HarpiaTest/`, not this folder.
- Treat as a roadmap / spec scratchpad. Read `Requisits.md` to understand intended end-state features; don't expect it to build.
