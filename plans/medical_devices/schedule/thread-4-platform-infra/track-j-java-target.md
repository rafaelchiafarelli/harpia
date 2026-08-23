# Track J — Multi-language codegen (Java, first target language)

**Restructured 2026-08-23: moved out of the medical_devices plan.**
Multi-language codegen (Java, and eventually Python) isn't
medical-devices-specific work — it was only ever *tracked* here because
`harpia_medical_master_plan.md` needed to reference "language #2" while
scoping compliance-aware emitters. The real, full session breakdown (10
sessions, J.1–J.27) now lives at
[`plans/multi-language-targets/thread-1-java-target/track-j-java-target.md`](../../../multi-language-targets/thread-1-java-target/track-j-java-target.md) —
that's the canonical source; don't duplicate its content here, it will
drift (the same failure mode this whole restructuring effort has spent a
session fixing elsewhere).

**Corrected 2026-08-23 (was stale):** this used to say Python, per
`plans/multi-language-targets.md`'s original recommendation. That file
(and `plans/java-target.md`) are both deleted now — their content moved
into the standalone `plans/multi-language-targets/` plan linked above.
See that plan's `README.md` §4 for the full Python→Java selection
history.

## What's actually medical-compliance-specific about this track

Almost nothing, structurally — the bulk of the work (J.1–J.27) is
general harpia capability, scoped and executed under the standalone plan
above with no dependency on this plan's Foundation. The one
compliance-specific concern, if this fleet's Java target needs to respect
`risk_class`/`phi` the way the C++ target eventually will:

- **Depends on:** F1 (`ComplianceContext` threading) from this plan's
  Foundation — only relevant if/when the Java emitters need to be
  compliance-aware, not a precondition for the base build.
- **Deliverable, layered on top of J.1–J.27:** whichever of the Java
  emitters handle `phi`/`risk_class`-gated behavior (encryption, RBAC,
  audit) need the same treatment their C++ counterparts get from Threads
  1/2/3 — not yet broken into its own sessions, since it depends on both
  J.1–J.27 existing *and* the relevant C++-side tracks (O/A/C/E) having
  already established the pattern to port.
- **Out of scope until both of those exist:** don't start scoping this
  layer's own sessions yet — genuinely blocked on two different threads'
  worth of prerequisite work landing first.

## Watch for

- If someone picks up Java target work, send them to the standalone plan
  first (`plans/multi-language-targets/`) — this file is a pointer, not
  a place to add session detail.
