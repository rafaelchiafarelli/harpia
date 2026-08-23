# Harpia Message Versioning: Surviving a Peer on a Different Schema

Status: §3 (Foundation) and §4 (Parse-boundary hardening) shipped
2026-08-22 — see §10/§11. §5 (capability handshake) fully shipped
2026-08-23 across all four transports (gRPC, REST/SOAP, ZMQ) — see §12/§13.
This plan's remaining real work is done; §6 is a cross-reference note, not
a task. Not medical-device-specific — this is a general
robustness property for any two Harpia-generated peers that don't get
redeployed in lockstep (a device in the field talking to a hub that shipped
a newer `.harpia` schema, two services on independent release cadences,
etc). One place it does intersect the compliance plan: once `risk_class`
implies medical-device-grade, an unhandled version mismatch can't resolve to
a silent no-op — that's the same "never silently swallow a failure mode"
rule as `harpia_sensitive_data_design_rules.md` Rule 5, just applied to a
new failure mode.

## 1. The actual hazard (found by reading the code, not assumed)

Harpia auto-assigns each field's wire number by **declaration order**, not
by anything stable:

```python
# message/Variables.py:141
var.index = len(self.variables)+1
```

Every message also gets a fixed `ID_<md5>` field forced to index 1
(`Variables.__init__`), and three hidden trailer fields — `STATUS_<md5>`,
`ERROR_<md5>`, `ORIGINATOR[_<md5>]` — appended *after* all user fields
(`AddHiddenVariables`). So there's already an implicit "reserved tail"
convention; it's just not extended to protect user fields from each other.

**Consequence:** inserting a field anywhere but the very end, or deleting
any field but the last one, silently reassigns the wire number of every
field declared after it. Protobuf's compatibility guarantees are keyed on
field *number*, not name — so this isn't a crash, it's **silent
misinterpretation**: an old peer reads a newer message's field 4 as if it
were still its own field 4, wrong type and meaning included. This is a
strictly worse failure mode than a parse error, and it's the thing this
plan exists to close off first.

Two things already in the codebase are relevant building blocks, not
starting points:
- **`renamed_from[old]` exists today** (`LexicalAnalizer/LexicalAnalyzer.py`
  token, `Variables.py:93-97`) but is wired **only** into
  `Database/MigrationAdapter.py` as a SQL `RENAME COLUMN` hint — it never
  touches the protobuf field number. It's the right vocabulary to extend,
  not a wire-versioning feature already built.
- **No `reserved`-style guard exists.** Nothing stops a deleted field's
  number from being silently reused by an unrelated new field, which is the
  worst case: a receiver interprets bytes for the old field's type as the
  new field's type.
- **No self-describing type/capability tag on the wire.** gRPC/REST/SOAP
  bind a message type at compile time (an unknown RPC method fails loudly —
  `UNIMPLEMENTED` or a build/link error, not silent). ZMQ pub/sub and raw
  proto streams have no such backstop today — a subscriber just gets bytes
  on a topic.

## 2. Three change categories, three different fixes

Confirmed as in-scope: additive field changes, whole message types
added/removed, and non-additive changes (rename/retype). They don't share
one mechanism.

### 2a. Additive fields — mostly free once field numbers are stable
Once a field's number is frozen at first ship (§3), proto3's own semantics
already do the work: an old peer parsing a newer message ignores fields it
doesn't know; a newer peer parsing an older message gets proto3 defaults
for fields the sender never set. No new machinery needed beyond confirming
Harpia's generated (de)serialization doesn't defeat this (§4).

### 2b. Whole message types added/removed — needs a capability signal
A peer has no way today to say "I don't know this message type" versus
silently failing to route/dispatch it correctly (worst on ZMQ, where
there's no compile-time backstop). Needs an explicit handshake (§5).

### 2c. Non-additive changes (rename, retype) — needs to become a hard error, not a silent bug
A rename should preserve the field's number (extend `renamed_from`, §3). A
genuine type change is a breaking change full stop — the fix is a new field
(new number, new name) plus a capability-gated translation shim (§5), not
an attempt to make an incompatible retype "just work" transparently. The
reserved-number guard (§3) is what turns an accidental retype-via-delete-
and-recreate into a hard generation-time error instead of the silent-
misinterpretation bug from §1.

## 3. Foundation — stable field identity (blocks everything else)

- **Freeze field numbers on first generation**, not on every regeneration.
  A sidecar file records `field name → wire number` the first time a
  message ships; regeneration reads it — existing names keep their number,
  a genuinely new field gets the next free number (not the next positional
  slot).
  - **Key by source location + message name, not `md5Hash`.** `md5Hash`
    changes on *any* edit to the file (see §8's old open question, now
    resolved) and — per `message/CLAUDE.md`'s documented gotcha — is
    shared across every message in a root file's import tree, a real
    collision risk for the upcoming multi-root-file feature. Neither
    property is safe to build a stable field-identity key on. Instead: one
    sidecar per message, stored at a path mirroring the declaring
    `.harpia` file's path relative to the project root, e.g.
    `schema_registry/<relpath-of-.harpia-file-without-ext>/<MessageName>.fieldmap`
    — both the file path and the message name are author-controlled and
    stable across additive edits by construction.
  - **Format** mirrors the plain-text sidecar convention `FileCreator`
    already uses for `.message`/`.variable` files (no new serialization
    dependency): one `name:number` line per field, plus a trailing
    `# reserved: 4,7` line for retired numbers.
  - **Moving or renaming a message itself** (not a field) has no fieldmap
    to carry forward automatically — that's a break in the key, not a
    field-level rename. Generation hard-errors and asks the author to
    either restore the original path/name or explicitly acknowledge a new
    message identity (fresh fieldmap, old one left in place as history) —
    consistent with Rule 5's "never silently correct" convention.
- **`reserved` tracking.** Deleting a field retires its number into the
  sidecar's reserved list. Regeneration hard-errors if any field — renamed
  or new — tries to reuse a reserved number. This is the direct fix for
  §1's worst case.
- **Extend `renamed_from[old]`** so it also carries the field's existing
  wire number forward, instead of `renamed_from` and wire-numbering being
  two unconnected systems that happen to both care about the same field.
  Database/MigrationAdapter.py's existing consumption is unaffected — it
  keeps doing the SQL `RENAME COLUMN` it already does.
- Recommend keeping `.harpia` syntax as-is (no `field = N` boilerplate) —
  the sidecar automates freezing without asking the schema author to
  hand-manage numbers, which is exactly the kind of bookkeeping a code
  generator should own.

**Tests:** unit — add/remove/reorder fields across two generations, confirm
numbers match the sidecar, not declaration order; reusing a reserved number
is a hard generation-time error; a `renamed_from` field keeps its number.
Integration — old-schema binary and new-schema binary exchange messages
over the real (de)serialization path; fields present in both decode
identically regardless of declaration-order drift between the two schemas.

## 4. Parse-boundary hardening (confirm, likely small)

- Audit that Harpia's generated (de)serialization code doesn't treat an
  unrecognized field as a parse error (proto3 default is tolerant —
  confirm nothing in the generated adapters overrides that).
- A proto3 default value (`0`, `""`, `false`) is ambiguous: "legitimately
  set to that" vs. "this field doesn't exist in the sender's schema." Where
  that ambiguity matters (`phi` fields especially — an absent `phi` field
  should never be misread as "explicitly cleared"), generate explicit
  presence tracking (proto3 `optional`). Confirm/align Harpia's existing
  `optional` modifier maps to proto3 presence semantics already, or needs
  adjusting.

**Tests:** unit — decode a message with an unknown trailing field, confirm
no error and known fields decode correctly; decode a message missing a
field the schema expects, confirm the presence signal (not just the zero
value) is what the generated accessor exposes.

## 5. Capability handshake — generated scaffolding, hand-written fallback

**A set, not a version number.** A single monotonic "schema version" implies
a total order — peer A is either behind, even, or ahead of peer B. That
breaks the moment two branches independently add different message types
before merging, or a hotfix backports one new type without the rest of a
release: "version 7" doesn't mean the same thing on every peer claiming to
be at 7. What every design in §2b/2c actually needs answered is narrower —
"does *this specific* peer understand *this specific* message type/field" —
so that's what gets advertised: each generated peer sends the **set of
message-type names** (stable author-given names, not hashes) it
sends/accepts, once, at connection time. A receiver checks set membership,
never an ordinal comparison.

- **Transport-specific carrying mechanism**, tied to a touchpoint each
  transport already has rather than inventing a new phase:
  - **gRPC** — a metadata header on the first call of a session. Build
    this one first (native support, least new plumbing) — same "prove the
    pattern once" precedent as not generalizing the DB-backend seam before
    Postgres was a real second case.
  - **REST/SOAP** — ~~carried once at session establishment (Track C's
    login/session-token issuance already exists as a natural point to
    piggyback on)~~ **correction, see §13**: Track C's login/session-token
    issuance is a `harpia_medical_master_plan.md` design for the
    *unstarted* compliance plan, not something that exists in the actual
    codebase (confirmed by grep before building this slice — REST/SOAP
    auth today is a stateless per-request `X-User`/`X-Pswd` header check,
    no session concept anywhere). There is nothing to piggyback on. Built
    as a standalone `GET <base>/capabilities` route instead, shared by
    REST and SOAP (both already register routes on the same
    `crow::SimpleApp`) — see `HttpCapabilityAdapter/`.
  - **ZMQ** — ~~no existing metadata channel; piggyback on Track B's
    `stream[#]` setup phase (already a distinct lifecycle step per
    `harpia_medical_master_plan.md` Track B)~~ **correction, see §13**:
    same issue — Track B's `stream[#]` setup phase doesn't exist in the
    actual `ZmqAdapter/` code either (confirmed by grep: zero hits outside
    the aspirational plan). Built as its own small REQ/REP request/reply
    exchange instead, reusing the same wire messages gRPC/HTTP already
    defined — see `ZmqCapabilityAdapter/`.
- **Bootstrapping against peers that predate this feature entirely.** A
  peer built before capability advertisement existed will not send one.
  This is resolved the same way as any other unhandled-mismatch case (Rule
  5): the *absence* of a capability response (handshake timeout, connection
  that never sends one, malformed frame) is itself a **named, observable
  outcome** — logged as "legacy peer, no capability set" — not inferred
  silently and not retried indefinitely. On that outcome, the peer is
  treated as supporting only the message-type set that existed the last
  time this project didn't have capability advertisement (i.e., the
  pre-feature baseline), so nothing sent to it can rely on a type it can't
  possibly know.
- Receiving/attempting to send a message type absent from the peer's set
  resolves to a **named, observable outcome** — never a silent drop —
  mirroring the existing "no silent drops" convention from
  `harpia_sensitive_data_design_rules.md` Rule 4a/5.
- Harpia generates the capability-check/dispatch scaffolding **and a named
  extension point**; it does not guess the business-logic fallback itself.
  Same division of responsibility as `AuditSink`'s no-op-stub-now/real-
  implementation-later pattern in the compliance plan: the schema author
  fills in "if peer lacks capability X, do Y" by hand, in one place,
  instead of every generated call site growing ad hoc capability-sniffing.

**Tests:** unit — dispatch table routes a message the peer's set covers
correctly, routes an unrecognized/uncovered type to the named fallback
hook, never to a silent no-op; a missing/timed-out capability response is
itself the "legacy peer" outcome, not an error and not a hang. Integration
— an old-schema client and a new-schema server (message type added on the
server side) complete a real handshake; the client's fallback hook fires
exactly once, observably, with the correct capability info; a genuinely
pre-feature legacy client (no handshake support at all) still completes a
baseline exchange instead of hanging or crashing.

## 6. Relationship to Track H (DB schema-evolution backlog)

Track H (`harpia_medical_master_plan.md` §2) is the same non-additive-
change problem — repeated-composed-field migration, rename/drop/type-change
— but for the **local DB schema across time on one machine**, not **wire
compatibility between two live, differently-versioned peers**. They should
share vocabulary (this plan's extended `renamed_from` and Track H's
transform types describe the same kind of change) but are independent
tracks: migrating a local DB says nothing about whether two live peers can
still talk to each other, and vice versa.

## 7. Suggested slice order

1. **Foundation (§3)** — field-number freeze + reserved tracking. Blocks
   everything else. Single session.
2. **Parse-boundary audit (§4)** — likely mostly confirmation + targeted
   `optional`/presence fixes. Can run right after Foundation.
3. **Capability handshake, gRPC first (§5)** — prove the pattern on one
   transport (metadata header, first call of a session) before replicating
   to REST/SOAP/ZMQ, same precedent as not generalizing the DB-backend seam
   before Postgres was a real second case.
4. **Capability handshake, remaining transports (§5)** — ~~REST/SOAP via
   Track C's session establishment, ZMQ via Track B's `stream[#]` setup
   phase — each already has the touchpoint this plan hangs the handshake
   on, so this is wiring, not new lifecycle design~~ **correction, see
   §13**: neither touchpoint exists in the actual codebase (both are
   `harpia_medical_master_plan.md` design for the unstarted compliance
   plan). Built standalone mechanisms instead — a shared HTTP
   `GET <base>/capabilities` route for REST/SOAP, a REQ/REP exchange for
   ZMQ — both reusing gRPC's wire messages, neither depending on Track B/C
   ever landing.

## 8. Resolved this session (2026-08-19) — kept here for the record

- **Sidecar fieldmap key** is source-file-path + message-name, never
  `md5Hash` — see §3. Closes what was open question 1.
- **No monotonic version number.** Replaced with a per-peer advertised
  **set** of supported message-type names, checked by membership, not
  ordinal comparison — see §5. Closes what was open question 2 by
  dissolving it: `md5Hash` vs. a hand-bumped integer was the wrong choice
  to be making in the first place, since neither actually answers "does
  this peer support this specific type," which is the only question that
  matters.
- **Per-transport carrying mechanism** decided for all four transports by
  reusing a lifecycle touchpoint each already has (gRPC metadata, Track C
  session establishment, Track B stream setup) rather than inventing a new
  phase — see §5. Closes what was open question 3.
- **Bootstrapping against pre-feature peers** — resolved as its own named
  outcome ("legacy peer, no capability set" → baseline type set), not left
  as a gap. This wasn't one of the original three open questions but
  surfaced while resolving open question 2 and needed an explicit answer
  before the capability-set design could be called complete.

## 9. Open questions

- **Resolved in practice by §12/§13's implementation, updating this
  bullet's premise**: there is no REST/SOAP "session" to cache the
  capability set at (§13 found the assumed session mechanism doesn't
  exist). As actually built, `negotiate()` is a plain function the caller
  invokes whenever it wants a fresh answer — nothing is cached by
  generated code at all, so "does the cache need refreshing" doesn't
  arise the way this bullet originally framed it. What IS still open: if a
  caller chooses to cache a `negotiate()` result itself (a reasonable
  thing to do, just not something Harpia does for them), that's entirely
  the caller's own invalidation problem, undocumented today. Low priority —
  flagged so it doesn't get silently assumed away, not because it's
  blocking anything.
- **Resolved by §12's implementation**: exact on-the-wire encoding is a
  `repeated string message_types` field on `capabilities_Response`
  (`Assets/proto/protofiles/capabilities_service.proto`), the same message
  reused as-is (JSON-serialized) for HTTP and (raw-protobuf-framed) for
  ZMQ. A bitset against a generated stable ordering was the only other
  option seriously considered and wasn't chosen — a plain string set is
  self-describing (no separate ordering table to keep in sync between
  peers) and the type-name lists here are small enough that the encoding
  efficiency a bitset would buy isn't worth that coupling.

## 10. Shipped this session (2026-08-22) — §3 Foundation

- `message/FieldMap.py`: `freeze(variables, harpiaFile, messageName)`,
  called from `Message.Process` right after `Variables.get()`, overwrites
  each field's provisional (declaration-order) `.index` with the frozen
  one. Sidecar path matches §3's design exactly:
  `schema_registry/<harpia file stem>/<MessageName>.fieldmap`, next to the
  declaring `.harpia` file (not under the build/output dir, which gets
  wiped wholesale on regeneration — see `tests/run_pipeline.py`).
- `reserved` tracking implemented: a name dropped from the sidecar between
  generations retires its number; `freeze()` hard-errors
  (`Types.RESERVED_FIELD_NUMBER_REUSED`) if any field's resolved number
  ever lands on a reserved one.
- `renamed_from[old]` extended to carry the wire number forward (inherits
  `old`'s number when `old` is on record). One deliberate deviation from
  the original wording: a `renamed_from[old]` with **no** record of `old`
  (first generation for the message, or `old` never existed) falls back to
  plain new-field numbering instead of hard-erroring — this turned out to
  be required, not optional: `HarpiaTest/Include/file3.harpia`'s
  `beacon_log.label` already ships a `renamed_from[handle]` where `handle`
  only ever existed as a hand-crafted fixture in the DB migration test,
  never as a real prior Harpia generation. Mirrors
  `Database/MigrationAdapter`'s own `renamed_from` handling, which is
  likewise a no-op (not an error) when the old column isn't actually live.
- **New wrinkle found (not anticipated in §3's original text) and closed
  in the same slice:** `ID_<md5>`/`STATUS_<md5>`/`ERROR_<md5>`/
  `ORIGINATOR[_<md5>]` carry the *whole file's* md5 in their own literal
  name, which changes on *any* edit to the `.harpia` file (confirmed by
  running the real front-end twice with only an unrelated field reorder
  between runs — see `tests/test_fieldmap_frontend.py`). Freezing by
  literal name would have read every single edit as "the old hidden field
  was deleted, an unrelated new one appeared," churning their wire numbers
  on every regeneration — the exact hazard this plan exists to close, just
  self-inflicted by the freeze mechanism itself. Fixed by keying these four
  fields by role (`ID`/`STATUS`/`ERROR`/`ORIGINATOR`) instead of literal
  name, reusing `Database/model.py`'s existing `_HIDDEN_PREFIXES`
  convention (duplicated locally in `FieldMap.py`, not imported — front-end
  code must not depend on the back-end).
- **Not implemented, deliberately** (see §3's own text — this was flagged
  as a corner case, not part of the Tests list): detecting a message
  *itself* being moved/renamed (as opposed to one of its fields). A
  message with no sidecar at its current path is indistinguishable from a
  genuinely brand-new message without extra bookkeeping this slice doesn't
  add; still an open gap, not a regression.
- Verified: a full pipeline run against `HarpiaTest/test.harpia` produces
  byte-identical `.proto` output vs. `tests/golden/proto` (first-generation
  freeze reproduces the existing declaration-order numbers exactly), and a
  second run is fully idempotent (sidecar content and mtimes unchanged).
  `HarpiaTest/schema_registry/` is now committed source (see
  `HarpiaTest/CLAUDE.md`).
- Tests: `tests/test_fieldmap.py` (unit, drives `FieldMap.freeze` directly:
  first-generation freeze, reorder/insert stability, delete-retires-
  number, rename-keeps-number, unresolvable-rename-falls-back, hidden-
  field-hash-change stability, reserved-number-reuse hard error, sidecar
  path shape) and `tests/test_fieldmap_frontend.py` (the same reorder/
  delete properties through the real front-end pipeline, two generations,
  fresh subprocess per run per the existing `run_frontend.py` convention).
  §3's "old-schema binary / new-schema binary real (de)serialization"
  integration test was added separately, same session, once Docker became
  available: `tests/test_message_versioning_wire.py` runs `main.py` twice
  against one root `.harpia` file (same sidecar both times), the second run
  reordering the message's existing fields and adding a new one; compiles
  gen1's protobuf class into a "writer" program and gen2's into a separate
  "reader" program, and proves a real serialized message round-trips
  correctly through actual protobuf wire encoding — fields present in both
  schemas decode to their original values despite the reorder, and the
  field only gen2 declares decodes to its proto3 default rather than
  colliding with either. Verified via `docker/run.sh`-equivalent (built
  the `harpia-build` image, ran without `-it` since this was a
  non-interactive invocation — see `tests/CLAUDE.md`'s TTY gotcha):
  `test_message_versioning_wire.py` plus the rest of the message-versioning
  and existing protoc/g++-gated suite (`test_stage7.py`, `test_stage8_db.py`,
  `test_golden.py`, `test_frontend.py`) all pass, 56/56. A full
  `pytest tests/` run in the same image surfaces 7 pre-existing failures
  (SOAP/REST/consumer/stage14) unrelated to this work — confirmed by
  reproducing one (`test_stage11_soap.py`) against a clean `git stash`
  of this session's changes: same failure, same cause
  (`third_party/asio` is missing `asio/detail/bind_handler.hpp`, a
  vendoring gap, not a message-versioning regression).

## 11. Shipped this session (2026-08-22) — §4 Parse-boundary hardening

Audited both of §4's bullets by reading every serialization path (protobuf
binary, JSON, XML) rather than assuming proto3's tolerant default held
everywhere — it didn't, on one path:

- **Unknown-field tolerance — one real gap found and fixed.** Protobuf
  binary (native `ParseFromArray`, used as-is by gRPC and ZMQ) and the XML
  runtime (`XmlAdapter/runtime/harpia_xml.h`'s `read_message`, which already
  skips an element with no matching field descriptor) were both already
  tolerant, no change needed. The **JSON adapter was not**:
  `JsonAdapter/templates/adapter.h.tmpl`'s `from_json`/`is_valid_json`
  called the single-arg `JsonStringToMessage` overload, whose default
  `JsonParseOptions.ignore_unknown_fields` is `false` — a JSON payload
  carrying one key the schema doesn't recognize (exactly a newer peer's
  added field) hard-failed to parse. Fixed by passing
  `JsonParseOptions{ignore_unknown_fields = true}` explicitly on both
  calls.
- **`optional` modifier — confirmed it needed adjusting, not just
  confirming.** The DSL's `OPTIONAL` token was parsed
  (`LexicalAnalizer/LexicalAnalyzer.py`) and stored on `variable.modifiers`
  (`message/Variables.py`) but reached nowhere past that — `FileCreator.py`
  never emitted proto3's `optional` keyword, so every field got proto3's
  ordinary implicit presence (no `has_<field>()`, `0`/`""`/`false`
  indistinguishable from "never set") regardless of the DSL modifier.
  Fixed in `protoFile/FileCreator.py`'s field-emission loop: a field
  carrying `OPTIONAL` (and not `REPETEABLE` — proto3 forbids `optional
  repeated`, so REPETEABLE wins if a schema somehow declared both) now
  emits `optional <type> <name> = <n>;`, giving it a real generated
  `has_<field>()`. `HarpiaTest/test.harpia` and its `Include/` files
  already used `optional` on six existing fields (`pope.xdr`, `king.sdfas`,
  `data.j`, `prince.val`, `queen.val`, `vip_users.name`) — this is a real,
  intentional `.proto`/JSON-adapter-comment output change on all six,
  captured by regenerating golden snapshots
  (`HARPIA_UPDATE_GOLDEN=1 pytest tests/test_golden.py`, reviewed diff:
  `optional` keyword added to 6 `.proto` files, the JSON adapter's
  `ignore_unknown_fields` change reflected in all 19 JSON adapter
  snapshots).
  - **XML needed a matching fix to not silently lose the new presence
    signal.** `harpia_xml.h`'s write path already gated singular-field
    emission on `HasField`, but only for `CPPTYPE_MESSAGE` — an `optional`
    scalar's absence would still round-trip as "present, at its default,"
    defeating the presence tracking just added at the `.proto` level.
    Generalized the existing check from `cpp_type() ==
    CPPTYPE_MESSAGE && !HasField` to `f->has_presence() && !HasField` —
    `FieldDescriptor::has_presence()` is true for exactly the two cases
    that need the gate (message fields, and now explicit-presence proto3
    `optional` scalars) and false for ordinary implicit-presence scalars
    (unchanged behavior for those, per the runtime's existing
    documented convention of always emitting scalar defaults).
  - **Deliberately NOT touched:** `Database/model.py`/`CrudlAdapter.py` —
    DB nullability is driven entirely by `REQUIRED`'s absence already
    (independent of `OPTIONAL`), and DB schema-evolution is explicitly
    §6's separate Track H concern, not this plan's. Scalar columns are
    still bound/read unconditionally regardless of an `optional` field's
    presence state; a NULL-vs-zero DB story for `optional` fields is a
    real gap but out of scope here.
- Tests: `tests/test_message_versioning_parse_boundary.py` — JSON tolerates
  an unrecognized key (known fields still decode); an `optional` field's
  `has_<field>()` correctly distinguishes "never set" from "explicitly set
  to the zero value" through both the raw protobuf binary round trip and
  the XML round trip (the latter specifically to prove the `has_presence()`
  runtime fix, not just protobuf's own already-correct JSON/binary
  machinery); a newer schema's added field, serialized by a "new" binary,
  parses cleanly on an "old" binary that has never heard of it (the inverse
  direction of §10's `test_message_versioning_wire.py`, same two-generation
  `main.py`-driven harness). All verified via `docker/run.sh`-equivalent
  (built the `harpia-build` image, ran without `-it` for this
  non-interactive session — see `tests/CLAUDE.md`'s TTY gotcha): 91 passed,
  2 skipped, the same pre-existing 7 `third_party/asio`-related failures
  from §10 (confirmed unaffected by this section's changes too — none of
  them touch `FileCreator.py`, the JSON template, or `harpia_xml.h`).

## 12. Shipped this session (2026-08-23) — §5 gRPC slice ("prove the pattern once")

Built the capability handshake for gRPC only, per §7's own order — REST/SOAP/
ZMQ are separate, not-yet-built slices. This is the first time Harpia
generates **client-side** gRPC code at all (every prior gRPC stage only
generated the server side; callers hand-wrote their own client against the
raw protoc stub — confirmed by reading `Database/GrpcServiceAdapter.py` and
`tests/test_stage13.py` before starting). Design choice made explicitly with
the user up front (§5 leaves the exact mechanism open, and §9 explicitly
delegates "exact on-the-wire encoding" to whoever builds this slice): a full
real handshake (dedicated RPC, real timeout, generated client-side
negotiation + dispatch) over a lighter metadata-only first pass, since the
plan's own Tests bullet ("missing/timed-out capability response," "client's
fallback hook fires exactly once") only really makes sense against a real
request/response with a deadline, not a per-call metadata tag with no
independent timeout.

- **New static wire contract** — `Assets/proto/protofiles/capabilities_service.proto`:
  `capabilities_Request` (empty), `capabilities_Response{repeated string
  message_types}`, `capabilities_Service{rpc GetCapabilities}`. Copied
  verbatim by `Util.util.copyBasicProtos` (extended to also copy this file),
  same treatment as `errorCode.proto`/`heartBeat.proto`. Named
  `*_service.proto` deliberately so `protoFile/GrpcCompiler.py`'s existing
  `*_service.proto` glob picks it up with no compiler changes.
- **New adapter, `GrpcCapabilityAdapter/`** (own top-level module, not under
  `Database/` — unlike `GrpcServiceAdapter` it never touches CRUDL/DB).
  `GrpcCapabilityAdapter(messages, dest, rootHash).Process()` emits exactly
  ONE `capabilities_<rootHash>_grpc.h` per project (not per-message, unlike
  every other Stage 13 adapter) implementing `capabilities_Service` to
  return `sorted({m.name for m in messages if not m.isEnum})` — every
  non-enum message type the schema declares, including table-less ones
  (capability is "does the peer's generated code know this type exists,"
  not "does it have DB backing," so this deliberately does NOT filter on
  `tableName` the way `GrpcServiceAdapter` does).
- **New hand-written runtime, `GrpcCapabilityAdapter/runtime/harpia_capability.h`**
  (copied verbatim into the build, same split as `XmlAdapter/runtime/harpia_xml.h`):
  - `negotiate(channel, timeout, on_legacy_peer)` — calls `GetCapabilities`
    with a real `grpc::ClientContext` deadline. Any non-OK status (peer
    never registered the service → `UNIMPLEMENTED`; peer never answers in
    time → `DEADLINE_EXCEEDED`; anything else) resolves uniformly to the
    plan's "legacy peer, no capability set" outcome: `on_legacy_peer()`
    fires exactly once, returns `std::nullopt` — never a hang, never a
    silent empty set.
  - `Dispatcher` — `on(type, handler)` + a **mandatory** fallback taken by
    the constructor (no default), so an uncovered type — or a covered type
    with no handler actually registered for it — structurally cannot reach
    a silent no-op. Same "harpia wires the capability, caller supplies the
    logic" split as `Database/MigrationAdapter`'s `data_transform` hook.
- **`GetCapabilities` is deliberately ungated** (no `x-user`/`x-pswd`
  check, like `heartBeat`) — gating "which types exist" would block the
  exact bootstrapping case (a client that doesn't yet know if it's talking
  to a legacy peer) the handshake exists to handle gracefully.
- **`prune_stale_outputs` fix required**: `capabilities_<hash>_grpc.h`
  matches the `<name>_<hash>...` orphan-detection regex but "capabilities"
  isn't a message name, so it would have been deleted-then-recreated every
  single run, defeating `write_if_different`'s mtime stability. Added
  `"capabilities"` to `Util.util._ALWAYS_VALID_BASENAMES` alongside
  `TestAdapter`'s existing `"app"` exception.
- **Deliberately NOT done this slice**: no wiring into `server_template`/
  `client_template` (the demo is ZMQ-only; per-message gRPC services aren't
  auto-registered there either, so this follows existing precedent rather
  than inventing new demo scope); REST/SOAP/ZMQ handshakes; any change to
  `Database/GrpcServiceAdapter.py`'s existing per-message services.
- Tests: `tests/test_message_versioning_capability.py` — `negotiate()`
  against a real in-process server gets back the actual schema's type set;
  `negotiate()` against a real generated project's server that has OTHER
  services registered (`prince_Service`) but not `capabilities_service`
  (a genuine pre-feature legacy peer, not just an empty server — an empty
  `ServerBuilder::BuildAndStart()` itself fails, so this is the realistic
  shape) resolves to the named legacy-peer outcome within the deadline;
  `Dispatcher` routes a covered type to its handler and falls back (never
  silently) both for an uncovered type and for a covered type with no
  handler registered. `tests/test_golden.py` gained a
  `test_capability_advertisement` check (mirroring `test_grpc_service_impls`)
  for the new `capability/` artifact dir. Verified via the same Docker
  image as §10/§11: 96 passed, 2 skipped, the same pre-existing 7
  `third_party/asio`-related failures, confirmed unrelated (none of them
  touch anything this slice changed).

## 13. Shipped this session (2026-08-23) — §5's REST/SOAP and ZMQ slices

Before writing any code, checked whether the touchpoints §5 (and §7's slice
order) named for REST/SOAP and ZMQ actually exist. **They don't.** Grepped
the real codebase (not just plans): no session/login mechanism anywhere in
`Database/RestAdapter.py`/`SoapAdapter.py` (auth is a stateless per-request
`X-User`/`X-Pswd` header check), no `stream[#]` setup phase anywhere in
`ZmqAdapter/`. "Track B"/"Track C" are names from
`plans/medical_devices/harpia_medical_master_plan.md` — a separate,
**unstarted** compliance plan §5 had conflated with something already
built. Flagged this to the user before proceeding (a real, consequential
correction, not a detail to silently paper over) rather than either
blocking on Track B/C landing first or inventing a fake session concept
just to match the plan's original wording. §5's own two bullets and §7's
slice-order bullet are corrected in place above (struck through, with
"see §13" pointers) rather than silently rewritten, so the discovery stays
visible in the doc's own history.

**Design chosen**: standalone capability-query mechanisms mirroring gRPC's
shape (a caller invokes `negotiate()` once, caches the result itself — no
"session" needed, since gRPC's own `negotiate()` never had one either),
reusing the exact same `capabilities_Request`/`capabilities_Response` wire
messages `capabilities_service.proto` already defined for gRPC — just
carried over a different transport:

- **REST/SOAP share ONE mechanism** (`HttpCapabilityAdapter/`), not two:
  a single `GET <base>/capabilities` route on the same `crow::SimpleApp`
  a real deployment already registers both REST and SOAP routes on (see
  `Database/RestAdapter.py`/`SoapAdapter.py`, both taking a
  `crow::SimpleApp&`) — building a redundant SOAP-envelope-specific
  capability operation would have been pure duplication for zero new
  coverage. The response is `capabilities_Response` serialized via
  `google::protobuf::util::MessageToJsonString` (reusing protobuf's own
  JSON support, symmetric with the client's `JsonStringToMessage` parse —
  sidesteps any hand-rolled JSON-compatibility question entirely, e.g.
  protobuf's default camelCase field-name mapping is handled identically
  by both ends automatically). Client runtime (`harpia_http_capability.h`)
  needed its own minimal blocking-socket HTTP GET-with-timeout helper
  since **Crow ships no HTTP client** (same reason
  `tests/harpia_test_client.h` already exists) — a trimmed, GET-only
  sibling of that test client, not vendoring a full client library.
- **ZMQ gets its own small REQ/REP exchange** (`ZmqCapabilityAdapter/`):
  a `capabilities_responder` (REP, bound at construction, `serve_once()`
  answers one query) and `negotiate()` (fresh REQ socket per call,
  `ZMQ_RCVTIMEO` for the real timeout, `linger=0` — the same `ZMQ_LINGER`
  gotcha already documented for CURVE in `ZmqAdapter/CLAUDE.md`). ZMQ's
  async connect/send semantics mean both normally succeed even against a
  peer that's never shown up (they just queue, by design) — `recv()`
  timing out is the one real signal a "legacy peer, no capability set"
  outcome can hang off.
- **`Dispatcher` extracted into a new shared module, `Capability/`**
  (`runtime/harpia_capability_dispatch.h` + a tiny `capability_common.py`
  for the two things genuinely identical across all three adapters: which
  types get advertised, and the shared runtime's path). It has zero
  gRPC-specific code — duplicating it three times the moment a second
  transport needed it would have been the wrong call. All three adapters
  now copy this one shared file into the same `generated/cpp/capability/`
  output directory alongside their own transport-specific
  `capabilities_<hash>_{grpc,http,zmq}.h` and `harpia_*_capability.h`.
  `GrpcCapabilityAdapter/runtime/harpia_capability.h` was trimmed down to
  `negotiate()` only as part of this extraction — a source change, not a
  behavior change (existing gRPC tests re-verified green after).
- **`prune_stale_outputs` fix from §12 already covered this**: `"capabilities"`
  in `Util.util._ALWAYS_VALID_BASENAMES` matches all three new filenames'
  shared `capabilities_` prefix, no further change needed there.
- **`tests/run_pipeline.py`'s golden-artifact collector had a real bug**,
  found and fixed in the same slice: `_collect_capability` originally
  excluded exactly one runtime filename (`"harpia_capability.h"`) by exact
  string match, written back when only the gRPC slice existed. Once HTTP
  and ZMQ added three more `harpia_*.h` runtime files, that exact-match
  exclusion silently let all three leak into `tests/golden/capability/` —
  static, hand-written files that don't need re-snapshotting (same
  reasoning as `_collect_xml` excluding `harpia_xml.h`). Fixed by matching
  on the actual distinguishing pattern (`capabilities_` prefix = generated,
  `harpia_` prefix = runtime) instead of an exact filename list that a
  second/third adapter would silently outgrow again.
- **Deliberately NOT done this slice**: no attempt to fix the pre-existing
  `third_party/asio` vendoring gap (missing `asio/detail/bind_handler.hpp`)
  that blocks compiling anything touching `crow.h` in this Docker image —
  confirmed pre-existing via `git stash` against a clean checkout before
  this session ever started (see §10), unrelated to message-versioning,
  and a real fix belongs in its own separate piece of work. This means
  `HttpCapabilityAdapter`'s two Crow-server tests currently fail in this
  environment for that same reason, not because the code is wrong — see
  the next bullet for how that was verified anyway.
- **HTTP slice verified in two pieces because of the asio gap**: (1) the
  generated route + `negotiate()` compile and link correctly against a
  local `crow.h` **stub** covering just the API surface used (isolates our
  code's syntax/logic from the vendoring issue); (2) `negotiate()`'s real
  networking + JSON parsing verified against a real Python `http.server`
  (success path, including the camelCase field-name round trip) and a real
  closed port (legacy-peer path) — both passed for real, no stub involved.
- Tests: `tests/test_message_versioning_capability_zmq.py` (2 tests, both
  pass for real — no crow/asio dependency): a real `inproc://`
  responder/negotiate round trip; a real `tcp://` port with nothing
  listening resolving to the legacy-peer outcome within the deadline (not
  `inproc://`, whose connect-before-bind semantics vary by libzmq
  version). `tests/test_message_versioning_capability_http.py` (3 tests):
  the unreachable-host case passes for real; the two real-Crow-server
  cases currently fail for the pre-existing asio reason above, not a code
  defect (see the stub/real-server verification above). `Dispatcher` is
  NOT re-tested per transport — it's the exact same class regardless of
  which `negotiate()` populated the `std::set<std::string>` passed to it,
  already covered in `test_message_versioning_capability.py`. Verified via
  the same Docker image as §10/§11/§12 (rebuilt to pick up the new
  modules): 99 passed, 2 skipped, 9 failed — the same 7 pre-existing
  failures from §10/§12 plus the 2 new Crow-dependent HTTP capability
  cases explained above; nothing else newly broken.
