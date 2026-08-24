### Session J.22 — Gradle packaging

- **Depends on:** J.2 merged (needs message classes to package).
- **Deliverable:** Gradle packaging (not Maven — deliberately, since
  Gradle is what Android app modules already use): `build.gradle`
  template, dependency declarations for whichever of J.1–J.21's libraries
  the generated project actually uses.
- **Tests:**
  - Integration: `gradle build` succeeds on a minimal generated project.

## Implementation notes (landed 2026-08-23) — already delivered incrementally, not built fresh here

Unlike the C++ track (where CMake packaging was its own late-stage
session), this thread's `GradleAdapter` (J.2) started the `build.gradle`
template on day one and every session since (J.3 grpc, J.4
protobuf-java-util, J.5 sqlite-jdbc, J.8 postgresql, J.18 jeromq, J.21
junit-jupiter) added exactly its own dependency line to the SAME file as
it went, rather than deferring all packaging to one big session at the
end. By the time this session was reached, `GradleAdapter/templates/
project.gradle.tmpl` already **is** "a `build.gradle` template, dependency
declarations for whichever of J.1-J.21's libraries the generated project
actually uses" — this session's literal deliverable, already true.

**Nothing new landed for J.22 specifically.** The stated test bar
("`gradle build` succeeds on a minimal generated project") is already
exercised repeatedly by this thread's own tests (e.g. `tests/
test_java_gradle_wiring.py::test_generated_message_classes_compile_and_
roundtrip`, and every other gradle+JDK-gated integration test added since
J.2, all of which run a real `gradle build` first). Recorded here for the
session-breakdown's own bookkeeping — a future reader of `../../README.md`
§6's 27-session list shouldn't read "J.22: not started" from this file's
absence of a dedicated adapter.

**Maven vs. Gradle, confirmed correct in hindsight:** the Android
motivation this choice was made for (`../../README.md` §7 — a harpia-
generated Java module becoming something an Android app module can depend
on with no build-system translation) held up across every later session;
nothing in J.3-J.21 needed walking it back.
