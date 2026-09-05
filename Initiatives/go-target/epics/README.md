# go-target — epics

13 epics. See `../README.md` §7 for the full contract table and §3 for what's
deliberately excluded (DDS, ZMQ-CURVE/ZAP).

## Order / dependency graph

```
lang-backend-seam (0)
        │
        ▼
go-foundation (1)
        │
        ├──► go-serialization (2) ──┐
        ├──► go-database (4)        │
        │                            ▼
        ├──► go-crypto-phi (3)  (needs 2 + 4: redaction lives in
        │                        serialization, encryption in DB)
        ├──► go-transports-http (5) (needs 4 for CRUDL-backed impls)
        ├──► go-zmq (6)
        ├──► go-events (7)
        └──► go-versioning (8)
                │
                ▼
go-discovery-fhir (9)     (needs 5's REST/SOAP shape for WS-Discovery,
                            needs 2's serialization for FHIR JSON)
go-artifacts (10)          (needs the others' file lists to enumerate — do late)
go-tests (11)              (needs 2/4 at minimum to have something to test)
        │
        ▼
tri-language-interop (12)  (needs 1–8 merged at minimum)
```

Within 3/5/6/7/8 there's no hard ordering against each other — pick based on
whichever is clearest to implement once 1/2/4 exist.

## Task-level planning status

**Only `lang-backend-seam` (epic 0) has task files written** — see
`lang-backend-seam/tasks/`. It's the immediate next epic once
`transport-multipeer-coverage` lands. Epics 1–12 are contract-level only
(the table in `../README.md` §7) until each is picked up — see that doc's §7
closing note for why.

## Definition of done (every epic)

- Its own epic's contract (the one-line summary in `../README.md` §7) is
  delivered and demonstrated by a real generated project, not just unit
  tests of the adapter in isolation.
- Full suite green in Docker, including the C++ and Java targets (the
  `lang-backend-seam` retrofit means a Go-target regression risk now
  technically runs through the same dispatch path Java uses — watch
  `golden_java/` on every epic, not just Go's own golden baseline).
- Any deliberately-reduced scope (mirroring Java's own embed/FK/map
  deferrals, `JavaDatabase/CLAUDE.md`) is disclosed in the epic's own
  `CLAUDE.md`/doc-comments, never silent.
- Ground Rule 6 doc-comments for any consumer-facing template the epic
  touches (see `../README.md` §6) — part of the epic's own Definition of
  Done, not deferred to a separate pass.
