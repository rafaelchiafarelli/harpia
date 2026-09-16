## Document the `protected` / `open` modifiers

- **Depends on:** tasks 1–4 shipped.
- **Deliverable:** update `harpia.process.md` (the `.harpia` grammar block
  and the Stage 5/access-credential section) and `USAGE.md` §8 ("Hardened
  transport") to describe `protected`/`open`, their per-transport scope
  (REST/SOAP/gRPC RBAC axis only — ZMQ/DDS explicitly not yet, per this
  epic's deferred scope), and the hard-error behavior when both are present
  on one message. Update `README.md`'s "No multi-tier RBAC" Known Gaps
  bullet to reflect what's now possible vs. still project-wide-only (ZMQ
  CURVE, DDS-Security).
- **Out of scope:** any further code change — docs only.
