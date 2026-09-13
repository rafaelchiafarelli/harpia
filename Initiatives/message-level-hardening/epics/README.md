# message-level-hardening — epics

One epic: **`protected-open-modifiers`** (`protected-open-modifiers/tasks/`).

## Task order

```
1-dsl-modifiers
        │
        ▼ (go/no-go: confirms the whole epic's approach before more code lands)
2-mtls-optional-mode-spike
        │
        ▼ (needs both 1's flags and 2's confirmed approach)
3-per-message-rest-soap-grpc-wiring
        │
        ▼
4-mixed-mode-fixture-and-tests
        │
        ▼
5-docs
```

## Definition of done (every task)

- Any message using neither `protected` nor `open` emits byte-identical
  `.proto`/generated-code output to before this epic — same guarantee
  `phi`/`critical`/`dds` already hold. This is the epic's core backward-
  compatibility bar; a task that can't hold it stops and flags rather than
  quietly accepting drift in the golden snapshots.
- Full suite green in Docker before merging up (`Docker/run.sh pytest
  UnitTests/`).

## Watch for

- **Task 2 is a go/no-go gate, not ordinary task work.** If Crow (or its
  underlying OpenSSL/asio setup) can't cleanly do "client cert requested, not
  required" with a reliable way to detect "connected, no cert presented" vs
  "connected, cert presented but didn't verify," stop and bring the finding
  back — don't improvise a workaround (e.g. two separate listening ports)
  into task 3 without confirming that's actually wanted first.
- **`protected` + `open` on the same message is a hard generation error**,
  same posture as `FieldMap`'s `RESERVED_FIELD_NUMBER_REUSED` — never a
  silent "one wins" precedence rule.
- **gRPC has no per-call TLS-optionality concept the way HTTP does** — a gRPC
  channel is TLS end-to-end or it isn't. Task 3 needs to confirm whether
  "open" for a gRPC message means "no RBAC role check" (identity still comes
  from the channel's mTLS, when present) or something stronger; this is
  likely a smaller version of task 2's question, worth resolving explicitly
  rather than assuming gRPC behaves like REST/SOAP here.
