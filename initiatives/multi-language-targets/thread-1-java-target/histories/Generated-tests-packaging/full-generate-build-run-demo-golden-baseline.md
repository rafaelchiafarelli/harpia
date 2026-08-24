### Session J.23 — Full generate → build → run demo + golden baseline

- **Depends on:** J.21, J.22 merged (and, practically, most of the
  emitter groups above — this is the track's integration point).
- **Deliverable:** nothing new — proves the whole surface works together.
- **Tests:**
  - Integration: full generate → `gradle build` → run demo, Java target,
    mirroring the existing C++ client/server demo.
- **Acceptance gate:** establishes its own golden-snapshot baseline
  (first of its kind for this target).

## Implementation notes (landed 2026-08-23)

**Golden baseline:** `tests/test_golden_java.py` + `tests/golden_java/`
(101 files) — one whole-`java/`-tree comparison (message classes' proto
inputs, every adapter's generated Java source, `build.gradle`/
`settings.gradle`), not split per subdirectory the way `tests/
test_golden.py` splits the C++ target's dozen output roots, since the
Java target's whole output is one coherent Gradle project. Also asserts
write-if-different (an unchanged regenerate doesn't touch `build.gradle`'s
mtime).

**"Nothing new" mostly held, with one honest caveat:** Gradle's `build`
task depends on `check` depends on `test` by default, so every
gradle+JDK-gated test this thread has run since J.2 already compiled the
ENTIRE `src/main/java` tree together (not just its own smoke file) and,
since J.21, already ran the full generated JUnit suite in the same build
— "the whole surface works together" was a continuously-checked property
throughout this thread, not something this session discovered for the
first time. The one genuinely new piece:
`tests/test_java_full_demo.py`'s cross-subsystem check, proving a REST-
created row is readable through the DB DAO directly (a separate JDBC
connection to the same SQLite file) — mirroring the actual POINT of the
C++ target's own client/server demo (independently-built pieces sharing
real backing state), not just each layer passing its own isolated test.

Neither test runs in this environment (no gradle/JDK here), same status
as every other Java integration test this thread has added.
