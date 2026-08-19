# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps.

## ZMQ CURVE encryption — done this session (see USAGE.md §10)

ZMQ was the last transport with zero security (REST/SOAP/gRPC all have TLS
and an `X-User`/`X-Pswd`-equivalent credential gate; ZMQ had neither).
Closed the encryption half: every generated sender/receiver/publisher/
subscriber constructor (`ZmqAdapter/templates/{sender,receiver}.tmpl`) now
takes a trailing, defaulted CURVE-keys struct (`CurveServerKeys`/
`CurveClientKeys`, defined once per header behind their own include guard).
Default/empty = today's plaintext behavior, byte-identical except for the
added constructor text (all 5 `tests/golden/zmq/*` fixtures regenerated and
diff-reviewed). Scoped via `AskUserQuestion` before planning: **encryption
only** (no ZAP client-key allowlist — any client with valid CURVE crypto is
accepted, the ZMQ analogue of TLS with no client certs, not mTLS), with
build-time ephemeral keypair generation.

Architecturally this differs from the REST/SOAP/gRPC TLS work: harpia never
generates the server-construction call for those, so "enabling TLS" was
pure caller-side build-enablement with zero generated-code changes. ZMQ's
`bind()`/`connect()` happen *inside* the generated classes, so this
necessarily touched the templates themselves.

Key generation: no CLI keygen tool ships with apt's `libzmq3-dev`, so
`Assets/cmake/curve_keygen_probe.cpp` (calls `zmq_curve_keypair()` twice) is
compiled+run via `try_run` from the root `Assets/CMakeLists.txt` at
configure time, gated behind a new `-DUSE_ZMQ_CURVE=ON` option (default
OFF). `Assets/vcpkg.json`'s `zeromq` dependency gained the `curve`+`sodium`
features for Windows parity (apt's libzmq on Linux already links libsodium
and has CURVE built in — confirmed via `zmq_has("curve")`, no apt change
needed).

**Two real bugs found and fixed, not just theoretical risks:**
- Z85-encoded CURVE keys can contain characters like `#`/`$`/`(`/`)` that a
  build system's command-line layer mangles (GNU Make treats `#` as a
  comment and `$` as a variable reference). First attempt passed keys
  through `target_compile_definitions` — three of four keys silently never
  reached the compiler (`'HARPIA_ZMQ_CURVE_SERVER_PUBLIC' was not declared`)
  despite the CMake-side value being correct. Fixed by writing a generated
  header (`harpia_zmq_curve_keys.h`, via `file(WRITE ...)`) instead, which
  sidesteps the shell/Make layer entirely.
- `ZMQ_LINGER` defaults to `-1` (block forever): a socket with an
  undelivered message from a failed CURVE handshake hangs on destruction.
  Caught for real while writing the negative-case test (a process that had
  already printed its final "recv failed as expected" line still didn't
  exit) — documented in `USAGE.md` §10 as a gotcha for anyone constructing
  a sender against a peer that might fail to authenticate.

Verified for real, not just "compiles": a live Docker demo build+run over
real `tcp://` (both server and client logged "CURVE enabled", message
crossed correctly); a new `test_zmq_curve_roundtrip` in
`tests/test_stage13_zmq.py` proving both directions (matching keys succeed
over real `tcp://` — CURVE is a no-op over `inproc`, so this needed a real
socket; a wrong server public key times out, proving CURVE actually rejects
bad crypto); a new `test_demo_message_crosses_with_curve` in
`tests/test_demo.py` building the full generated project with
`-DUSE_ZMQ_CURVE=ON` via its own CMake and running server+client over
`ipc://` (also a real ZMTP handshake, unlike `inproc`). Full suite: 77
passed, 2 skipped (both pre-existing opt-in live-Postgres tests), no
regressions.

**Not covered, left as a follow-up:** Windows build-verification. The vcpkg
feature is added (`Assets/vcpkg.json`) and the `try_run` probe is written to
use `find_package(ZeroMQ CONFIG)`'s `libzmq` target on `WIN32` (same
CONFIG-vs-bare-library-name gotcha the demo targets themselves already
handle), but nothing has actually been built on the native Windows host —
only Linux/Docker is verified this session.

## Cross-version data transforms — done this session (see USAGE.md §6)

`migrate_<name>` moved column *structure* forward (rename/add/drop/retype)
but never *values* — no way to backfill a computed value (e.g. derive `age`
from `birthdate`, split a retiring `full_name` into `first_name`/
`last_name`) on upgrade. Scoped via `AskUserQuestion` before planning:
**caller-supplied C++ hook, not new `.harpia` syntax** — harpia's DSL is a
deliberately flat, non-recursive grammar (the `renamed_from[<old>]`
precedent needed one atomic lexer token specifically to dodge the generic
`[...]` bracket machinery; a separate GUI-DSL prototype was rejected for
needing a richer recursive grammar), so arbitrary value logic can't live in
the DSL itself. Same "harpia wires the capability, caller supplies the
logic" precedent as TLS/CURVE.

`migrate_<name>` gained one trailing, defaulted parameter:
`std::function<void(::soci::session&)> data_transform = nullptr`. Passing
nothing preserves today's behavior exactly. This turned out to be a
**template-only change** — `Database/MigrationAdapter.py`'s `_render()`
needed zero edits (no new DSL marker feeds it, so there's no new per-column
logic to generate); only `Database/templates/migrate.h.tmpl` changed
(`#include <functional>`, the signature, and one static call site).

**Non-obvious design fact found while scoping, not just an implementation
detail — gets the motivating "split a column" case wrong if missed:** the
hook must run **after ADD, before DROP**, not at the very end. Reasoning
through "split a retiring `full_name` into `first_name`/`last_name`" makes
this concrete: ADD must already have created `first_name`/`last_name` for
the hook to write into, and DROP must not yet have removed `full_name` or
the hook has nothing left to read. Structural order is now: RENAME → ADD →
**transform hook** → DROP → RETYPE → stamp version.

Verified via a new `test_migration_data_transform` in
`tests/test_stage8_db.py` (same hand-seed-an-older-schema-then-migrate
pattern as the existing rename/drop/retype tests, reusing the `beacon_log`
fixture — no new `.harpia` fixture needed): derives `label` from a retiring
`full_label` column the current schema doesn't declare at all, proving (a)
the hook actually ran between add and drop (the derived value is correct
AND the old column is gone afterward), (b) the hook is genuinely optional
(a second row migrated with no hook argument doesn't crash on the empty
`std::function`), and (c) idempotency (a second call with the same hook
doesn't corrupt an already-transformed row). All 9 `tests/golden/migrate/*`
fixtures regenerated and diff-reviewed — exactly the signature + call-site
+ comment change, nothing else. Full suite green.

## Other open items (see README.md "Known gaps" for the full/current list)

- PostgreSQL backend on Windows — only SQLite is verified there;
  `soci[postgresql]` was never added to the vcpkg manifests.
- True crash/interrupt recovery (resume a *killed mid-run* generate) — the
  sha256-registry/marker half of `harpia.architecture.md`'s "continuable
  process" that the write-if-different work explicitly did not attempt.
  Still just spec text, no design started.
- Python as language #2 — `plans/multi-language-targets.md` has the scoped
  recommendation. Multi-session sized, don't start as a "quick session."
- Smaller/unscoped: no YAML serialization, no Doxygen generation, no
  multi-tier RBAC (single flat credential everywhere).

## Reminder for whoever picks this up

`git log --oneline origin/dev..dev` to check nothing's local-only (should be
empty — everything as of this file's commit is pushed).
`[[harpia-dev-workflow]]` memory has the test/golden-file workflow;
`[[harpia-project-status]]` memory has the full session-by-session history.
`[[harpia-git-case-insensitive-gotcha]]` matters again for any commit
touching `Message/`, `Logger/`, `ProtoFile/`, or `Util/` — verify with
`git diff --stat HEAD` after committing, not just `git status`.
