# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps.

## Windows as a generated-code target — done this session (see USAGE.md §11)

The candidate gap from the previous session is closed: the generated C++
project (not `main.py` itself, which still only runs via Docker/Linux)
builds and runs natively on Windows (MSVC 2022 + vcpkg), verified for real
— not just "compiles" — for both the ZMQ server/client transport demo and
the REST/JSON demo (`examples/consumer`, including `-DUSE_TLS=ON` with a
real TLS 1.3 handshake). Three genuine source-level Windows-compat bugs got
fixed along the way (protobuf version skew between Docker's baked codegen
and vcpkg's runtime; a protobuf `Reflection` API shape change breaking
`XmlAdapter`; a Crow/`windows.h` `DELETE` macro collision that silently
drops Crow's ALL-CAPS `HTTPMethod` enum members) — see `USAGE.md` §11 for
the full writeup and the CLAUDE.md files it points at for exactly where.

**Not covered, left as follow-ups:**
- The Stage 14 generated `ctest` suite (`-DHARPIA_BUILD_TESTS=ON`) —
  `tests/harpia_test_client.h` (its REST/SOAP HTTP round-trip test client)
  is plain POSIX sockets (`arpa/inet.h`, `sys/socket.h`, `fcntl.h`,
  `unistd.h`), unrelated to either demo above. Porting it would be a third,
  separate surface.
- PostgreSQL backend on Windows — only SQLite is verified; `soci[postgresql]`
  was never added to the vcpkg manifests and nothing was tested against a
  real Postgres server from Windows.
- **Antivirus false positives are real, not hypothetical** — this session
  hit Avast quarantining/locking a freshly-built, unsigned,
  network-listening `server.exe` mid-session (rebuild failed with
  `LNK1104: cannot open file`, no live process holding it). Needed a
  manual antivirus exclusion before the ZMQ demo could be verified.
  Documented in `USAGE.md` §11 as a known gotcha for future readers hitting
  the same thing.

## Other open items (see README.md "Known gaps" for the full/current list)

- Cross-version **data transforms** — `migrate_<name>` moves column
  *structure* forward (rename/add/drop/retype) but never *values*: no way to
  backfill a computed value (e.g. derive `age` from `birthdate`, split
  `full_name`) on upgrade. Needs a design decision (new DSL syntax vs. a
  user-supplied C++ hook `migrate_<name>` calls out to) before any code —
  scope via `AskUserQuestion` first.
- SSL/TLS on **ZMQ** (CURVE) — REST/SOAP/gRPC already have TLS; ZMQ has
  neither encryption nor any credential gate at all today (checked:
  `ZmqAdapter` has no `x-user`/`x-pswd`-equivalent check, unlike the other
  three transports). First step is just verification: does the
  apt-installed `libzmq` even have CURVE (needs libsodium) built in. Note
  from a prior session's discussion: CURVE is a poor fit for constrained
  embedded targets (ATmega2560 can't run libzmq/libsodium at all regardless
  of crypto choice; ESP32 is more plausible but libzmq's own security
  mechanisms don't compose with ESP-IDF's native mbedTLS) — if the goal is
  ever "talk to small devices securely," that's a separate transport/
  security problem, not a CURVE extension. Explicitly deprioritized by
  Rafael this session in favor of Windows.
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
