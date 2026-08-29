## `dds` grammar support

Scoped 2026-08-29. **Task 1** of the dds-transport epic. Well-specified as
written; this pass only pins the pre-work and confirms it's a plain modifier.

- **Depends on:** F1 (Foundation).
- **Deliverable:** new `dds` transport-modifier value in
  `LexicalAnalizer/`/`Message/`, composable the same way `push`/`pull`/
  `event`/`stream` are today — a message picks `dds` when it needs to be
  published onto/read from a DDS bus, independent of whether it's also
  reachable via ZMQ or gRPC. **Plain modifier — no bracket parameter**
  (mirrors `push`/`pull`/`event`; the lexer gets `('DDS', r'dds ')`,
  `Message.py` treats it exactly like the other transport modifiers).
- **Pre-work (inside this task):** add a `dds`-tagged message to
  `HarpiaTest/Include/file3.harpia` — an Include-file edit moves golden
  *content* for that message but leaves every pinned `HASH` alone
  (`epics/README.md` "Watch for"). Regenerate with
  `HARPIA_UPDATE_GOLDEN=1` and review. Compose it with `phi` on one field
  so task 4's audit test has a fixture.
- **Tests:**
  - Unit: `dds` composes correctly with `phi`, `optional`, `repeteable`
    per existing modifier-composition tests
    (`UnitTests/test_phi_modifier.py` / `test_critical_modifier.py` shape).
  - Integration: the emitted `.proto` for a `dds` message is line-for-line
    identical to the same message without it — `dds` is a routing flag, it
    never touches the wire format (same guarantee `phi` / `critical` hold).

---
## Epic context — dds-transport

**Contract.** A new `dds` transport modifier, a `DdsAdapter/` module mirroring
`ZmqAdapter/`, QoS mapping for `critical`/non-`critical` messages, and DDS-Security
wiring via the `CryptoBackend` seam. A third selectable transport alongside gRPC
and ZMQ (ASTM F2761 / OpenICE-class bedside bus), not a replacement. Needs
`ComplianceContext`, the `AuditSink` stub, and the `CryptoBackend` seam from
Foundation.

**Files.** New `DdsAdapter/`; `LexicalAnalizer/` and `Message/` for the `dds`
grammar.

**Open question (not scoped).** Deadline QoS (DDS detecting a publisher missing
its period) is new territory beyond the design rules §4 — whether a periodic
stream wants a schema-level `deadline[ms]` modifier needs a domain-expert pass
before it is scoped. Do not invent the name/semantics here.

**Watch for.** The DDS implementation choice (vendor TBD, e.g. Eclipse Cyclone
DDS) blocks every task after the adapter core — pick one deliberately there, do
not leave it as a follow-up.
