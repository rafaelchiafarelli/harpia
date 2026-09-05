## `main.py` dispatches through the registry; full regreen

- **Depends on:** tasks 1 and 2 (`cpp` and `java` backends both exist).
- **Deliverable:**
  - `main.py`'s `if genLang == "java": ...` inline block (and the
    unconditional C++-path stages, once identified as "the `cpp` backend's
    job") replaced with a single dispatch through `get_lang_backend`.
  - `HARPIA_GEN_LANG` behavior is externally identical: unset/`cpp` behaves
    exactly as before, `java` behaves exactly as before, an unknown value
    gets a clear error (this is new — today an unrecognized `HARPIA_GEN_LANG`
    silently falls through to the C++-only path with no Java block; decide
    whether that's worth preserving as `cpp`'s own fallback behavior or
    tightening to a hard error, and record the choice here once made — this
    is exactly the kind of decision the `harpia-workflow` skill says not to
    make implicitly, so flag it to Rafael rather than picking silently).
- **Deliverable (verification):** full suite green in Docker
  (`Docker/run.sh pytest UnitTests/`), with explicit attention to:
  - `UnitTests/test_golden.py` and `UnitTests/test_golden_java.py` — byte
    identical, zero diff.
  - Every `test_java_*.py` file passes (gradle+JDK-gated ones need the
    Docker image's JDK 17 + Gradle 8.5).
  - `UnitTests/test_incremental_regen.py` — write-if-different behavior
    (mtime stability on an unchanged rerun) survives the dispatch change,
    since that test is sensitive to exactly this kind of refactor
    accidentally touching output files.
- **Out of scope:** registering `go` (that's `go-foundation`, epic 1).
- **Tests:** the full suite, as above — this task's entire job IS the
  regreen, there's no narrower test to write.
