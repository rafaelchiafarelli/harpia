## Spike: can one REST/SOAP server serve both gated and anonymous routes?

- **Depends on:** nothing (independent of task 1; can run in parallel).
- **This is a go/no-go gate, not ordinary feature work.** Its deliverable is
  a written finding, plus a minimal throwaway/reference proof, not
  production wiring — task 3 depends on the answer, not on this task's code.
- **Question to answer:** can Crow (as vendored under `third_party/`, the
  same build used by `HarpiaTest/app_example/consumer -DUSE_TLS=ON`) be
  configured so a client cert is **requested but not required** — i.e. the
  TLS handshake succeeds either way, and the handler can reliably distinguish
  "connected with no cert" from "connected with a cert that failed to
  verify"? `Database/auth_gate.py`'s `authz_*` helpers already treat an empty
  `req.client_cert_cn` as anonymous — confirm that's actually what an
  unpresented-cert connection produces under requested-not-required mode,
  as opposed to the connection being refused outright or the CN field being
  ambiguous between "no cert" and "cert present but CN empty."
- **Also answer for gRPC:** gRPC's channel-level TLS has no per-call
  optionality the way HTTP does. Confirm whether "open" for a gRPC message
  can mean "skip the RBAC role check, allow calls with no verified peer
  identity" without weakening the channel's own TLS requirement (if any) —
  this is a smaller, related question, not the same spike infrastructure.
- **Deliverable:** a short written finding (a markdown note in this task
  file or a linked doc) stating: works as needed / works with caveats (name
  them) / doesn't work, plus whichever minimal proof-of-concept code backs
  the finding. If the answer is "doesn't work cleanly," stop here and bring
  the finding back — do not have task 3 improvise a fallback (e.g. two
  listening ports) without that being a separate, explicit decision.
- **Out of scope:** any change to `Database/auth_gate.py` or the adapters
  (task 3) — this task only establishes feasibility.
