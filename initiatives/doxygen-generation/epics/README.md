# Doxygen Doc-Comment Coverage — Epic

Restructured 2026-08-24 from `../doxygen-generation.md`, mirroring the
per-track breakdown used in `initiatives/medical_devices/epics/`: a
`README.md` (this file) plus `histories/<topic>/track-X-<name>.md` +
`histories/<topic>/tasks/*.md`, one small session per file, each sized to
fit a single sitting.

Only one track here (**Track D**), because only one body of work is left.
`../doxygen-generation.md`'s own status note explains why: **F6** (the
mechanical Doxyfile/CMake/mainpage plumbing) already shipped and merged to
`dev` 2026-08-23 — see `../../medical_devices/epics/handoff-document.md`'s
F6 section. What's left is `../doxygen-generation.md` §3/§4: real,
per-template Doxygen doc-comments (not generic boilerplate) landing in the
consumer-facing headers the generator emits.

- [track-d-doc-comment-coverage.md](histories/doc-comment-coverage/track-d-doc-comment-coverage.md) —
  doc-comment content for every consumer-facing template/adapter, keyed off
  `../doxygen-generation.md` §4's pitfall table.

---

## Why this is a *fallback* track, not a normal one

`../doxygen-generation.md`'s **Ground Rule 6** says this work is supposed
to happen incrementally, inside whichever `medical_devices` track next
touches a given adapter/template — not as a separate deferred effort.
That's still the preferred path: a session in Track A, B, C, F, etc. that
touches `CrudlAdapter`/`XmlAdapter`/`ZmqAdapter`/etc. should land the
matching doc-comment in the same sitting, per that track's own Definition
of Done.

This track exists for two reasons Ground Rule 6 alone doesn't cover:

1. **A trackable checklist.** Without it, "did the doc-comment land" is
   only answerable by re-reading every other track's diffs. Track D's
   sessions below double as that checklist — one per adapter/template
   group, cross-referencing which `medical_devices` track is expected to
   cover it.
2. **A real owner for gaps.** Some templates (`protoFile/FileCreator.py`'s
   message/field templates, the shared generated-file banner) aren't in
   *any* medical_devices track's Files-touched list — nobody's session
   will land them opportunistically. Track D is where those get done
   directly.

**Before picking up any session below:** check whether the "expected
covered by" track named in that session has already merged the work
(`git log`, that track's own `ComplianceReport/` note, or a quick grep for
the doc-comment text). Only do it here if it hasn't landed, or if the
session says no other track is expected to cover it.

---

## What this epic receives

- **F6, shipped** — `Assets/Doxyfile`, the CMake `doxygen` target,
  `Doxygen/mainpage.py` (assembles `USAGE_EXCERPT.md` from `USAGE.md`
  §4/§6/§11 at generation time), and the gated `tests/test_doxygen_docs.py`
  zero-warnings check. **Flag, still true as of this restructuring:** that
  test is proven only against a synthetic fixture — no generated template
  in the repo emits real `///`/`/** */` doc-comments yet. Track D's own
  sessions are what eventually gives it a real generated tree to point at
  (closed out in D's last session).

## Execution order across sessions

Sessions are independent of each other (different files) except the last,
which is a closing sweep:

```
D.1 -> ) all independent, any order/parallel
D.2 -> )
D.3 -> )
D.4 -> )
D.5 -> )
D.6 -> )
              v
             D.7  (closing sweep — needs D.1-D.6, or their
                    Ground-Rule-6 equivalents elsewhere, merged)
```

## Definition of done (every session in this track)

- The doc-comment's *content* matches the specific pitfall text in
  `../doxygen-generation.md` §4 (or the session's own description) — not
  generic boilerplate copy-pasted across templates.
- A golden-style snapshot test (mirroring `test_golden.py`) asserting that
  specific content, per `../doxygen-generation.md` §6 — so a later
  refactor can't silently regress it back to boilerplate without a test
  noticing.
- If the session's work surfaces a consumer-relevant pitfall not already
  in `../doxygen-generation.md` §4, add a row there in the same session
  (living-reference instruction, §4's preamble).

## Watch for

- Don't duplicate work another track already did under Ground Rule 6 —
  see "Why this is a fallback track" above.
- `WsdlAdapter` (D.5) has no clearly expected owner among the current
  medical_devices tracks — flag this again if you pick it up and nothing's
  changed.
