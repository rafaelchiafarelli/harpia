# go-target — epics

13 epics. See `../README.md` §7 for the full contract table and §3 for what's
deliberately excluded (DDS, ZMQ-CURVE/ZAP).

## Order / dependency graph

```
python-target/lang-backend-seam   (moved there 2026-10-03; prerequisite)
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
                            needs 2's serialization for FHIR JSON. Candidate
                            for python-target's 2026-10-03 re-scope to
                            WS-Discovery only (C++ has no FHIR façade) —
                            Rafael's call when Go is picked up)
go-artifacts (10)          (needs the others' file lists to enumerate — do late)
go-tests (11)              (needs 2/4 at minimum to have something to test)
        │
        ▼
quad-language-interop (12) (needs 1–8 + python-target's tri-language-interop)
```

Within 3/5/6/7/8 there's no hard ordering against each other — pick based on
whichever is clearest to implement once 1/2/4 exist.

## Task-level planning status

**No epic here has task files.** Write them when Go is picked up, adapting
`Initiatives/python-target/epics/*/tasks/` (same epic shapes, minus DDS and
CURVE/ZAP, pure-Go dependency rules instead of Python's).

## Definition of done (every epic)

Source of truth: `Initiatives/python-target/epics/README.md`'s "Definition
of done (every epic)" — moved there 2026-10-03 because Python ships first.
Apply it with `golden_go/` for `golden_python/`, `go vet` + `staticcheck`
for `mypy --strict` + `ruff`, and Doxygen/godoc comments for Sphinx
docstrings. Not restated here so the two can't drift.
