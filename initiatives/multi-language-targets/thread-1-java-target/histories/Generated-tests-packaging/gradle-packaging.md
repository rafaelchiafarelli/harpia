### Session J.22 — Gradle packaging

- **Depends on:** J.2 merged (needs message classes to package).
- **Deliverable:** Gradle packaging (not Maven — deliberately, since
  Gradle is what Android app modules already use): `build.gradle`
  template, dependency declarations for whichever of J.1–J.21's libraries
  the generated project actually uses.
- **Tests:**
  - Integration: `gradle build` succeeds on a minimal generated project.
