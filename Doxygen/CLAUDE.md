# Doxygen — mainpage assembly for the generated project's Doxygen docs (Foundation F6)

**Pipeline role:** Generation-time only. Assembles the Doxygen `@mainpage`
content for a generated project from slices of harpia's own `USAGE.md`,
written fresh every run to `<dest>/USAGE_EXCERPT.md`. The rest of F6 (the
`Doxyfile`, the CMake `doxygen` target) lives in `Assets/` -- see
`Assets/CLAUDE.md` and the F6 section of
`Initiatives/medical_devices/epics/handoff-document.md` (the Foundation
thread itself was merged to `dev` and removed; see git history for the
original implementation write-up).
**Entry points:** `write_mainpage(dest, usage_md_path=None, sections=(4,6,11))`
-> path written; `extract_usage_sections(usage_md_path=None, sections=...)`
-> assembled markdown string (the piece `write_mainpage` persists).

## Files
- `mainpage.py` — `_extract_section(text, number)` (private: pulls one
  `## N. Title` heading + body, up to the next top-level `## ` heading or
  EOF), `extract_usage_sections()`, `write_mainpage()`.

## Key facts / gotchas
- **Assembled fresh every run, not a static copy.** The F6 deliverable text
  says the mainpage should be "assembled from the relevant slice of
  USAGE.md ... referenced, not re-authored, so there's one place to keep
  the narrative accurate." A hand-copied static duplicate would still be
  able to drift the moment `USAGE.md` changes and nobody remembers to
  re-copy it; extracting the real section text at generation time instead
  means there's nothing to remember -- the next run's mainpage always
  matches whatever `USAGE.md` §4/§6/§11 currently say.
- **Section boundary detection is purely `## N. ` heading-prefix matching**
  (`DEFAULT_SECTIONS = (4, 6, 11)`, matching `USAGE.md`'s exact heading
  numbers, verified as an exact string match -- no renumbering was needed).
  Fragile to `USAGE.md` renumbering its top-level sections; if that ever
  happens, update `DEFAULT_SECTIONS` here to match.
- Cross-references inside the extracted USAGE.md prose (e.g. a relative
  link to `HarpiaTest/app_example/consumer/README.md`) are copied as-is and may not
  resolve correctly from inside an arbitrary generated project's own
  location on disk. Acceptable for F6's one-time-plumbing scope; not
  fixed here.
- `write_mainpage` uses `Util.util.write_if_different` (mtime-preserving),
  same convention as every other generated artifact.

## Touchpoints
- Called by: `main.py`, `UnitTests/run_pipeline.py` (both call
  `Util.util.copyDoxygenFiles` for the static `Doxyfile`, then
  `write_mainpage` for the assembled one).
- Depends on: `Util.util.write_if_different`; reads `USAGE.md` at the repo
  root (via `DEFAULT_USAGE_MD`, path-resolved off `__file__` so it works
  regardless of the caller's cwd).
- Tested by: `UnitTests/test_doxygen_mainpage.py` (pure Python, the extraction
  logic itself) and `UnitTests/test_doxygen_docs.py` (doxygen/cmake-gated, the
  real Doxyfile + CMake target end to end).
