# Message-Level Hardening: Mixing Protected and Open Messages In One Project

**Status: scoped, not started.**

## 1. Why this exists

Every credential/RBAC/mTLS gate today reads one project-wide boolean,
`Crypto.backend.transport_hardening_required(compliance)` — computed once per
generated project from `risk_class`/`topology` in `project.harpia.yaml` and
passed identically into every message's REST/SOAP/gRPC auth code
(`Database/auth_gate.py`, called from `RestAdapter.py`/`SoapAdapter.py`/
`GrpcServiceAdapter.py`). This is deliberate (`Compliance/context.py`: "a
single project-wide hardening floor, no per-message override") but it means a
project is all-or-nothing: fully gated, or fully open. There's a real need for
both in the same project — e.g. a health-check/catalog endpoint that should
stay open even in an otherwise-hardened project, or one sensitive message that
needs gating even in an otherwise-open one.

**Not the same problem as DB segregation.** `Database/DbRegistryAdapter.py`'s
PUBLIC/PRIVATE table visibility (`} table_name;` with a trailing `;` →
PRIVATE, no `;` → PUBLIC, per `Message/Message.py`) governs whether *another
generated Harpia project* may read this table — a cross-project data-ownership
ACL. It says nothing about whether a project's own clients need a credential
to call a message's REST/SOAP/gRPC endpoint. This initiative is about the
latter.

## 2. What's already true (verified by reading the code, not assumed)

- The auth code generators already run **per message** —
  `rest_auth_fills(msg.name, msg.md5Hash, rbac)` etc. are called once per
  message in a loop. Only the `rbac` value itself is currently forced uniform
  across every call. Making it per-message is wiring, not a rewrite.
- The DSL already has four precedents for exactly this shape of feature —
  `phi`, `critical`, `dds`, `event[...]` — each a message-level modifier
  parsed once in `Message.py`, exposed as a boolean/enum attribute, read by
  downstream adapters, with a hard guarantee that a message using *none* of
  them emits byte-identical output to before the modifier existed.
- `harpia::rbac::decide(cn, op, "{name}")` already takes the message name as
  an argument (a per-resource decision point), and the REST/SOAP/gRPC
  `authz_*`/`rbac_check` helpers already treat an empty/absent client-cert
  CommonName as "unauthenticated" rather than crashing or defaulting to
  allow — the plumbing an "anonymous connection, gated per-route" model needs
  already exists.

## 3. Design decisions (made now — flag any of these you want changed)

- **Two new message-level modifiers, `protected` and `open`**, same slot as
  `critical`/`dds` (before `message`, trailing-space lexed, composes freely
  with transport-kind modifiers). Semantics:
  - Neither present → inherit the project-wide default (today's behavior,
    unchanged — this is what keeps every existing fixture byte-identical).
  - `protected` → this message's REST/SOAP/gRPC endpoints require the
    RBAC/session gate **regardless of** the project-wide setting.
  - `open` → this message's endpoints skip the gate **regardless of** the
    project-wide setting.
  - Both on the same message → hard generation-time error (same "never
    silently swallow a failure mode" convention as `FieldMap`'s
    `RESERVED_FIELD_NUMBER_REUSED`) — not a silent precedence rule.
- **Phase 1 scope: REST/SOAP/gRPC's RBAC/session axis only.** ZMQ CURVE and
  DDS-Security are explicitly deferred to a later epic (see below) — they're
  per-socket/per-participant rather than per-request, and CURVE key
  distribution + DDS-Security participant identity are different enough
  mechanisms that folding them in now would blur this epic's contract.
- **mTLS itself is the one open technical risk.** TLS/mTLS negotiates at the
  *connection* level, not per-request, so "require a client cert" is normally
  a whole-server setting — you can't have Crow demand a cert for one route
  and not another at the TLS layer. The plan is: run the server with the
  client cert **requested but not required**, and let the per-message RBAC
  check treat "connected without a cert" as anonymous (already how an empty
  `client_cert_cn` behaves) for messages that resolve to open, while
  `protected`/hardened-default messages still refuse an anonymous caller.
  **This needs a spike to confirm Crow/OpenSSL actually support
  "requested-not-required" the way we need — task 2 below, before any other
  task depends on it working.**

## 4. Scope

**In scope, now:** one epic, `protected-open-modifiers`:
- The DSL grammar + `Message.py` front-end (flag only, byte-identical output
  for any message using neither modifier).
- The mTLS-optional-mode spike (task 2 — a go/no-go gate for the rest of the
  epic; if Crow can't do this cleanly, stop and bring the finding back before
  task 3 proceeds).
- Wiring `Database/auth_gate.py` + the three adapters to compute the gate
  per-message instead of once per project.
- A mixed-mode test fixture: a hardened project with one `open` message, and
  an unhardened project with one `protected` message, proven over all three
  transports.

**Out of scope, deferred to a later epic:**
- ZMQ CURVE per-message (CURVE keys are currently a per-socket constructor
  parameter driven by the same project-wide flag — architecturally closer to
  per-message than REST/SOAP/gRPC's mTLS, but a separate design pass).
- DDS-Security per-message/per-topic.
- Any UI/tooling for authoring `HARPIA_RBAC_MAP` role assignments — unrelated
  to this initiative, already shipped as-is.

## 5. Non-goals

Not a new authentication *mechanism* — reuses the existing flat-credential /
RBAC-role / bearer-session machinery unchanged. This initiative only changes
**which messages** that machinery applies to, never how it decides once
applied.

## 6. Epics

One epic for now: **`protected-open-modifiers`** (`epics/README.md`). A
second epic for ZMQ/DDS per-message hardening is deliberately not scoped yet
— revisit once phase 1 ships and the mTLS spike's findings are in.
