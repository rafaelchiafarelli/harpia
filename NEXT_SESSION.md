# Next session

`README.md`'s "Known gaps" section is the live, authoritative list of
feature/perf gaps. This file adds one more candidate gap that isn't in
README yet — Windows as a generated-code target — scoped enough during a
conversation to be worth picking up, but not yet started.

## Windows as a generated-code target

Rafael asked how hard it would be for harpia to generate code that builds on
Windows. Investigated (not implemented): smaller problem than it sounds on
"does it compile," bigger than it sounds on "is there an actual build path."

**Broken today (small, contained fix):** `ZmqAdapter/templates/header.h.tmpl`'s
`runtime_origin_id()` — the runtime-unique sender id used by PUSH/PUSHPULL
messages (Message/CLAUDE.md's "shared/many-to-* publisher" case) —
unconditionally does `#include <unistd.h>` and calls `::getpid()`. Neither
exists under MSVC. This is the *only* place harpia's own generated code (as
opposed to vendored/example files) touches POSIX unconditionally. Needs an
`#ifdef _WIN32` branch to `GetCurrentProcessId()` (from `<windows.h>` or
`<process.h>`'s `_getpid()`).

Note: `Assets/external_libs/httplib.h` and `Assets/*_http_example/` are full
of raw POSIX socket code but are dead weight — grepped, nothing in the
Python adapters references them. Not a real blocker; candidate for deletion
in its own cleanup pass, unrelated to Windows work.

**Actually missing (the real work):** no verified Windows build path exists
at all. Every dependency harpia relies on already has Windows support
(gRPC, Protobuf, SOCI, ZeroMQ, Crow, tinyxml2 — typically via vcpkg), so
harpia would not need to port any of them itself. But:
- No vcpkg manifest/toolchain file.
- No MSVC CMake generator ever exercised — `docker/run.sh` and the whole
  test suite target the Linux Docker image exclusively.
- The Python test harness spawns C++ demo processes and reads stdout
  incrementally (recall the `std::endl`-flush bug found during the TLS
  work, session 4) — needs auditing for Windows subprocess/signal
  semantics, since that assumption was written and only ever tested on
  POSIX.
- `examples/consumer`'s `-DUSE_TLS=ON` self-signed cert generation shells
  out to the `openssl` CLI via CMake `execute_process` — unverified on
  Windows (vcpkg ships `openssl.exe`, but the invocation itself is
  untested there).

**Sizing:** bounded/scopeable, not epic-sized like the Python-language-target
work (`plans/multi-language-targets.md`). Needs an `AskUserQuestion` scoping
pass before planning — same pattern as data-transforms and ZMQ/CURVE below —
since "how much Windows support" (compiles vs. CI-verified vs. officially
supported) changes the size a lot.

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
  from this session's discussion: CURVE is a poor fit for constrained
  embedded targets (ATmega2560 can't run libzmq/libsodium at all regardless
  of crypto choice; ESP32 is more plausible but libzmq's own security
  mechanisms don't compose with ESP-IDF's native mbedTLS) — if the goal is
  ever "talk to small devices securely," that's a separate transport/
  security problem, not a CURVE extension.
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
