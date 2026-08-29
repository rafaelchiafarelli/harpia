## DDS implementation: spike + vendor commit

Scoped 2026-08-29. **Task 2a** of the dds-transport epic — split out from
`dds-adapter-qos-mapping` during planning because "pick + vendor a full DDS
stack" is real code and likely more than one session's worth on top of the
adapter itself (skill rule: pre-work needing code / >1 session becomes its
own task). Everything after this task is blocked on it — the epic's "Watch
for" already flags the vendor choice as the gate.

### Decision (settled during scoping)

- **Starting candidate: Eclipse Cyclone DDS** (Eclipse project, Apache-2.0,
  C core + `ddscxx` C++ binding, OMG DDS-Security plugins built in and
  OpenSSL-backed so they map onto the F5 `CryptoBackend` seam; the
  de-facto choice in OpenICE / ROS2-adjacent medical work).
  **The commit is this task's**, not planning's — per the epic, "prove the
  interface is real before committing to one." If the spike shows Cyclone
  DDS doesn't fit the adapter interface or the cross-board build posture,
  fall back to **eProsima Fast DDS** (Apache-2.0, C++-native, heavier
  dependency tree) and record why in this file.

### Contract

- **Depends on:** task 1 (`dds-grammar-support`) merged.
- **Deliverable:**
  1. A throwaway spike: exercise the candidate's publish/subscribe +
     QoS-setting API against the shape `DdsAdapter/` will need (a
     `<name>_publisher` / `<name>_subscriber` pair, per-message QoS
     profile, CURVE-equivalent security hook). Confirm it's real, not a
     paper API.
  2. Commit a vendor. Vendor its source into `third_party/<name>/` with a
     `VENDORED.md` (version, source URL, license) in the exact shape the
     other `third_party/*` entries use — `ComplianceReport/components.py`
     will pick it up for the SBOM automatically once the manifest entry is
     added.
  3. A **build-verified minimal pub/sub** in the Docker toolchain (add the
     DDS build deps to `Docker/Dockerfile` if needed — that image change
     is part of this task) — one message crosses between a publisher and a
     subscriber process, nothing generated yet.
  4. Add the new component to `ComplianceReport/components.py` (`VENDORED`
     or `ENVIRONMENT` as appropriate) so the SBOM lists it.
- **Out of scope:** `DdsAdapter/` codegen, QoS *mapping* logic,
  DDS-Security, `phi` audit — those are tasks 2b / 3 / 4.
- **Tests:**
  - Integration: the minimal pub/sub round-trip builds and runs in the
    harpia Docker image.
  - `ComplianceReport` golden updated (`HARPIA_UPDATE_GOLDEN=1`) to show
    the new SBOM component; diff reviewed.

**Watch for.** Cyclone DDS is a real C build (CMake), not a header-only
drop like `asio`/`tinyxml2` — expect a Dockerfile change and a longer
`third_party/` tree. If the vendored build fights cross-board toolchains,
that is a signal to reconsider the vendor here, not to patch around it in
2b.

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
