# Sensitive-data implementation roadmap (`phi` + `critical`)

Execution order for making `harpia_sensitive_data_design_rules.md` real. This
doc sequences the master-plan tracks (`harpia_medical_master_plan.md` §5) into
one dependency-ordered path and fills the one hole the master plan assumes away:
**`critical` has no track** — the plan says "the existing `phi`/`critical`
modifiers" everywhere, but Foundation F2 only ever shipped `phi`.

Scope for this effort: **full** — redaction AND envelope encryption AND
audit-on-access AND the `risk_class` hardening floor. Branch:
`feature/sensitive-data-implementation` (off `dev`).

---

## Definition of done

Stricter than "nothing old broke". Per master-plan §4, and confirmed with the
project owner, every phase below is done only when:

1. **Unit tests** for each new construct/behavior it introduces.
2. **One integration test** exercising the phase end-to-end on a realistic
   path. The two headline integration tests for the whole effort:
   - **`critical` send/receive** — a `critical` message survives a simulated
     transient transport outage (held in a bounded queue, replayed in order on
     reconnect; rotation logged on overflow) while a non-`critical` message is
     allowed to drop.
   - **`phi` send/receive** — a `phi` field round-trips through persist →
     process restart → read: the decrypted value matches the original, a raw
     SQL query bypassing the DAO shows ciphertext not plaintext, and exactly
     one `AuditSink` record is emitted per DAO op touching the field. Plus the
     serialization side: `toString`/JSON/XML/YAML redact `phi` values by
     default; the unredacted-output flag itself emits an audit record.
3. `UnitTests/test_golden.py` (+ `test_golden_java.py`) regenerated and the
   diff reviewed.
4. A one-paragraph traceability note into `ComplianceReport/` for any phase
   touching `phi`-adjacent code (F, A, C, E).

Fixture: `HarpiaTest/Include/file3.harpia` — `patient_vitals` (the `phi`
fixture) and `alarm_event` (`critical event`, added Phase 1a). Extend these two
messages rather than forking parallel fixtures (handoff-doc guidance).

---

## Dependency graph

```
Foundation F1-F6  .......................................  DONE (plumbing only)

1a  critical modifier (lexer + AST)  ── no prereqs
        └─► 3a delivery-guarantee runtime ─► 3b ZMQ wiring ─► 3c critical send/receive test

1b  Track O  key management (KeyProvider, KEK/DEK envelope, rotation, shred)  ── F1,F3,F5
1c  Track H  DB schema-evolution (repeated-composed, non-additive transforms)  ── none
        1b + 1c ─► 2b Track A  encrypt phi columns + audit-on-access ─► 2c Track K

2a  Track F  phi redaction in JSON/XML/YAML toString  ── F2 only  (independent, early)

4   Track C  mTLS + RBAC   ── F1,F3,F5   }  arm the risk_class floor
    Track B  ZMQ CURVE + stream lifecycle ── F1  }

5   Track M skeleton (ComplianceReport/, needed early for traceability notes)  ── F1
    Track N  static/fuzz CI gate on generated output  ── none
```

Reaching *just the two headline tests*: **1a + 1b + 1c + 2a + 2b + 3a + 3b +
3c**. Phases 4–5 complete "the full story".

---

## Phases

### Phase 0 — groundwork
- **`critical` fixture** — add `critical event message alarm_event` beside
  `patient_vitals` in `file3.harpia` (Rule 0: `critical` and `phi` are
  independent axes, so `alarm_event` carries both). Regenerate goldens.
- **`project.harpia.yaml`** — a checked-in repo-root config so a real
  generation run sees non-default `risk_class`/`topology` flow through instead
  of the missing-file/strictest fallback. **Deferred to Phase 1b** (Track O is
  the first code that actually branches on `ComplianceContext`; adding the
  file earlier, ahead of any consumer, only risks silent test interference for
  no functional gain — F1 is plumbing-only today).

### Phase 1a — `critical` modifier  ← current
Mirror Foundation F2's `phi` work, one level up (message-type, not field):
- `LexicalAnalizer/LexicalAnalyzer.py` — `('CRITICAL', r'critical ')`, a
  keyword-only modifier token, trailing space, same shape as `EVENT`/`STREAM`.
- `Message/Message.py` — `Message.is_critical` bool, set when `CRITICAL`
  appears in `access_modifiers` (dedicated flag so later stages don't re-scan
  the token list — same rationale as `variable.is_phi`).
- Flag only: no delivery machinery lands with this token; the emitted `.proto`
  is byte-identical to the same message without `critical`.
- Tests: `UnitTests/test_critical_modifier.py` — parse with/without `critical`,
  composed with `event`/`stream`/`push`/`pull`, order-independence, `critical`
  + `phi` on one message; `.proto` unaffected. Via an extended
  `run_phi_check.py` (now also reports per-message `is_critical`).

### Phase 1b — Track O: key management
Contract: master-plan §5 "O". `Crypto/KeyProvider` ABC (generate/fetch KEK,
wrap/unwrap DEK, rotate), envelope encryption (per-record DEK, KEK wraps DEKs),
crypto-shred, key zeroization, every key op through `AuditSink`, a default
TPM/keystore provider that forces acknowledgment under a PHI-at-scale profile,
one mock-KMS reference adapter. FIPS certification explicitly out of scope
(document the crypto-module choice, don't complete certification).
Also lands the deferred `project.harpia.yaml`.

### Phase 1c — Track H: DB schema evolution
Contract: §5 "H". Repeated-composed-field migration; non-additive transforms
(rename/drop/type-change) in `migrate_<table>()`. Pre-existing debt, no
compliance dependency.

### Phase 2a — Track F: serialization + redaction
Contract: §5 "F". `YamlAdapter/`; unified `toString` across JSON/XML/YAML;
`phi` values redacted by default in all three; the unredacted-output flag
emits an `AuditSink` record. Only needs F2 — can run in parallel with 1b/1c.
Delivers the serialization half of the `phi` send/receive test.

### Phase 2b — Track A: DB field-level encryption + audit
Contract: §5 "A". `EncryptedColumn<T>` on `is_phi` columns via Track O's
envelope scheme; DAO encrypt-on-write / decrypt-on-read through `KeyProvider`;
exactly one `AuditSink.record()` per DAO CRUDL op touching a `phi` field.
Delivers the `phi` send/receive test.

### Phase 2c — Track K: public/private DB segregation
Contract: §5 "K". Environment-level public/private DB registry; cross-project
private access denied.

### Phase 3a — delivery-guarantee runtime (transport-agnostic)
A generated runtime header, shaped like
`Capability/runtime/harpia_capability_dispatch.h` (hand-written, copied verbatim
into generated output):
- `Envelope{seq, crc, deliveryTimestamp}` — CRC computed once at origin
  (Rule 3), verified only at trust-boundary crossings (arrival / departure),
  never re-checked between internal steps.
- Bounded **rotating queue** (Rule 4a): fixed capacity; on overflow rotate
  (drop oldest) and emit a named rotation event through `AuditSink` — never a
  silent drop, never unbounded growth.
- **2-slot mailbox** / double-buffer (Rule 4b): latest-value-only; on overwrite
  emit a named event.
- No plausibility/range checks on payload values (Rule 2 — that's the
  acquisition layer's contract, not delivery's).

### Phase 3b — ZMQ wiring
`ZmqAdapter/` emits the runtime and routes each message by modifier: a
`critical` message type → the 4a rotating queue on the send path; others →
4b mailbox or straight passthrough (unchanged behavior). `is_critical` from
Phase 1a selects the path.

### Phase 3c — `critical` send/receive integration test
Real ZMQ socket (`inproc://` or `tcp://`) + a simulated stall: assert the
`critical` message is held and replayed in order on reconnect, a rotation
event is logged when the bounded queue overflows, and a non-`critical`
message on the same path is dropped rather than queued.

### Phase 4 — the `risk_class` floor
- **Track C** (§5 "C"): mTLS on gRPC/REST/SOAP; admin/main/guest RBAC
  replacing the flat `X-User`/`X-Pswd` gate; token sessions with
  expiry/revocation; cert-provisioning scripts in `Assets/`. Plaintext
  refused once `risk_class` implies medical-device-grade — for *every*
  message, not just tagged ones (§6a).
- **Track B** (§5 "B"): ZMQ CURVE + full `stream[#]` lifecycle
  (setup/read/stop, timeout, dead-connection reclamation).

### Phase 5 — traceability + CI gate
- **Track M** skeleton: `ComplianceReport/` module (SBOM, traceability
  matrix). Stand up early so Phases F/A/C/E notes have a real home.
- **Track N**: cppcheck/clang-tidy CERT ruleset + fuzz harness for the
  JSON/XML/SOAP parsers, as a CI gate on generated output. Required clean for
  Tracks A/C/K once the floor is in place.

---

## Notes carried from scoping

- `critical` is **message-type-level**, never per-field, never a payload value
  the transport reads (design-rules §0 / §7 — content-based execution is the
  anti-pattern being ruled out). If a device must bundle an alarm-worthy
  reading with routine telemetry, the fix is two message types, not a runtime
  criticality field.
- One code path, never per-jurisdiction (§0a). `jurisdiction[]` only selects
  Track M's paperwork template.
- ECC-RAM assumption behind "no CRC re-check between internal steps" (Rule 3):
  document the target-hardware dependency, don't silently assume it.
