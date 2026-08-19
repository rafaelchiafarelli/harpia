# Harpia Message Versioning: Surviving a Peer on a Different Schema

Status: scoped, not started. Not medical-device-specific — this is a general
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
  - **REST/SOAP** — carried once at session establishment (Track C's
    login/session-token issuance already exists as a natural point to
    piggyback on) and cached for the session's lifetime, rather than
    repeated on every stateless call.
  - **ZMQ** — no existing metadata channel; piggyback on Track B's
    `stream[#]` **setup** phase (already a distinct lifecycle step per
    `harpia_medical_master_plan.md` Track B) as the capability-exchange
    point, rather than adding a second handshake concept.
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
4. **Capability handshake, remaining transports (§5)** — REST/SOAP via
   Track C's session establishment, ZMQ via Track B's `stream[#]` setup
   phase — each already has the touchpoint this plan hangs the handshake
   on, so this is wiring, not new lifecycle design.

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

## 9. Open questions (not yet resolved)

- Whether the REST/SOAP capability set, once cached at session
  establishment (§5), needs a way to be refreshed mid-session if a service
  is hot-upgraded without dropping existing sessions — not yet a concrete
  requirement, flagged so it doesn't get silently assumed away.
- Exact on-the-wire encoding of the capability set (e.g. a repeated string
  field vs. a bitset against a generated stable ordering) — a real
  engineering choice for whoever builds §5's Foundation slice, not decided
  here since it doesn't change any guarantee in this doc either way.
