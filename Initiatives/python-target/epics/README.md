# python-target — epics

13 epics. See `../README.md` §4 for the full contract table, §2 for why
Python needs no DDS/CURVE exclusion (unlike `go-target`), and §6 for why no
epic here has task-level files yet.

## Order / dependency graph

Same shape as `go-target`'s (`Initiatives/go-target/epics/README.md`) — this
mirrors it deliberately rather than inventing a different structure:

```
py-foundation (1)   [registers into go-target's LangBackend seam, doesn't rebuild it]
        │
        ├──► py-serialization (2) ──┐
        ├──► py-database (4)        │
        │                            ▼
        ├──► py-crypto-phi (3)  (needs 2 + 4)
        ├──► py-transports-http (5) (needs 4)
        ├──► py-zmq (6)
        ├──► py-events (7)
        ├──► py-versioning (8)
        └──► py-dds (9)             (no Go equivalent — see ../README.md §4)
                │
                ▼
py-discovery-fhir (10)   (needs 5 + 2)
py-artifacts (11)        (do late — needs the others' file lists)
py-tests (12)            (needs 2/4 at minimum)
        │
        ▼
quad-language-interop (13)   (needs go-target's tri-language-interop, epic 12, merged)
```

## Definition of done (every epic)

Identical bar to `go-target`'s (`Initiatives/go-target/epics/README.md`'s
own Definition of Done), substituting `golden_python/` for `golden_go/` and
Sphinx doc-comments for Doxygen ones. Not re-stated here to avoid the two
initiatives' DoDs silently drifting apart if only one gets edited later —
that file is the source of truth for the shape, this initiative follows it.
