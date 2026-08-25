## Session E.3 — `AuditSink` hook on `OnChange` + full round-trip

- **Depends on:** E.1, E.2 merged; F3's `AuditSink`.
- **Deliverable:** `AuditSink` hook fires on `OnChange`, specifically for
  `phi` fields; one-paragraph `ComplianceReport/` note (feeds Track M
  later).
- **Tests:**
  - Integration: subscribe → mutate → assert the callback fires with the
    correct payload, and for `phi` fields an audit record is emitted.
- **Acceptance gate:** new functionality, no prior behavior to preserve —
  100% pass on this track's own new tests.