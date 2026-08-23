### F6 — Doxygen infrastructure (added 2026-08-23)

Folded in from `initiatives/doxygen-generation/doxygen-generation.md`, which used to be its own
scoped-but-not-started track. Re-scoped: the one-time plumbing below is
Foundation's job; the ongoing "every template emits accurate doc-comments
for what it renders" discipline is Ground Rule 6 above, applying to every
track from here on — not something Foundation builds once and forgets.
`initiatives/doxygen-generation/doxygen-generation.md` itself stays alive as a living pitfall-table
reference (its §4), not a finished/removed plan — see that file's own
2026-08-23 status update.

- **Deliverables:** `Doxyfile` + CMake `doxygen` target
  (`add_custom_target`); `@mainpage`/`USE_MDFILE_AS_MAINPAGE` pointed at a
  landing page assembled from the relevant `USAGE.md` slices (§4 "What
  gets generated", §6 "Wiring the generated code into your own project",
  §11 "Notes & limits") — referenced, not re-authored, so there's one
  place to keep the narrative accurate.
- **Guarantees:** `doxygen` target builds HTML docs from the generated
  tree without needing any per-project configuration from the consumer.
- **Out of scope:** the per-template doc-comment content itself (Ground
  Rule 6's job, not this deliverable's); usage-example-as-integration-test
  generation (`initiatives/doxygen-generation/doxygen-generation.md` §5, a separate, larger,
  explicitly-deferred project).
- **Tests:**
  - A `doxygen`-gated test (skipped when the `doxygen` binary is absent,
    same pattern as the C++-toolchain-gated tests in `tests/CLAUDE.md`)
    that runs `doxygen` over a generated project and asserts zero
    warnings with `WARN_IF_UNDOCUMENTED = YES` — this is what makes
    Ground Rule 6 mechanically enforceable rather than just a written
    convention: a track that forgets a doc-comment fails this test, not
    just a review.
  - Acceptance gate: this test stays green as every later track lands —
    a regression here means some track's session skipped Ground Rule 6.
