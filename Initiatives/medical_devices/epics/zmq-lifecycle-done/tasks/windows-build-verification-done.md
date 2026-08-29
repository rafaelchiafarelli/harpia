## Windows build-verification (existing CURVE feature)

> **DONE 2026-08-29.** Verified from a WSL2 session driving the host's
> Windows toolchain over interop (VS 2022 Community / MSVC 2022 + vcpkg
> `zeromq[curve,sodium]` + Windows CMake): the generated demo project
> configures with `-DUSE_ZMQ_CURVE=ON`, builds `server.exe` + `client.exe`,
> and a real `tcp://127.0.0.1` CURVE client→server message exchange
> succeeds (`[client] CURVE enabled` … `[server] received: {"i":7,…}`).
> The plaintext demo was built + run alongside as the control.
>
> **Two Windows-only bugs in `Assets/CMakeLists.txt`'s CURVE branch were
> found and fixed as part of this task** (Linux `else()` branch untouched):
>
> 1. **`LNK1104: cannot open file 'libzmq.lib'`** at configure — the keygen
>    `try_run` was handed the bare imported-target *name* `libzmq`, which its
>    isolated sub-project can't resolve. Fixed by resolving the `ZeroMQ`
>    CONFIG target to a concrete `IMPORTED_IMPLIB_*` / `IMPORTED_LOCATION_*`
>    path + `INTERFACE_INCLUDE_DIRECTORIES`, and prepending its `bin/` to
>    `ENV{PATH}` for the probe's run step.
> 2. **`0xC0000409` crash at demo startup** — `try_run`'s
>    `RUN_OUTPUT_VARIABLE` keeps `\r\n` on Windows and the `[^ \n]+` regex
>    folded a trailing `\r` into each Z85 **secret** key; libzmq rejects the
>    41-byte value, cppzmq throws, `std::terminate`. Fixed by
>    `string(REPLACE "\r" "" …)` before parsing.
>
> Docs: `USAGE.md` §10/§12 + `Assets/CLAUDE.md` updated (gap → verified +
> the two fixes). No new pytest — the Linux `test_zmq_curve_roundtrip` /
> `test_demo_message_crosses_with_curve` already cover CURVE semantics; the
> Windows build+exchange is the artifact, same shape as the
> Postgres-on-Windows resolution.
>
> **Separate finding, NOT fixed here (out of scope):** on the current vcpkg
> baseline (protobuf 6.33.4) the plaintext demo runs fine, so protobuf-6.x
> itself is OK on Windows — but see `gaps-not-yet-tracked.md` if a
> protobuf-version-drift issue surfaces elsewhere.

- **Depends on:** nothing from this epic — this verified the
  **already-shipped** CURVE transport, not tasks 1–2's new work.
- **Deliverable:** build and verify the CURVE-enabled ZMQ demo on native
  Windows (MSVC + vcpkg) — done, plus the two CMake fixes above.
- **Tests:** the build + a real CURVE-enabled client/server exchange on
  Windows *is* the test — passed.
---
## Epic context — zmq-lifecycle

**Contract.** Full `stream` lifecycle (setup/read/stop, timeout, dead-connection
reclamation) on top of the already-shipped CURVE transport. Needs only
`ComplianceContext` from Foundation. No downstream consumer named. (The ZAP
client-key allowlist that used to round out this epic moved to the
transport-authn epic on 2026-08-29 — see that epic's README.)

**Already shipped, verify only:** CURVE-secured sockets + ephemeral keypair
provisioning (`-DUSE_ZMQ_CURVE=ON`, `Assets/cmake/curve_keygen_probe.cpp`). See
`USAGE.md` §10 and `ZmqAdapter/CLAUDE.md`. Do not rebuild.

**Files.** `ZmqAdapter/`. Tests to extend: `UnitTests/test_stage13_zmq.py`
(`test_zmq_curve_roundtrip`), `UnitTests/test_demo.py`
(`test_demo_message_crosses_with_curve`).

**Watch for.** (a) Z85 CURVE keys corrupt silently through
`target_compile_definitions` — use a generated header, never compile-definitions
for key material. (b) `ZMQ_LINGER` defaults to `-1`: a socket with an undelivered
message from a failed handshake hangs on destruction forever — applies to
the dead-connection reclamation sweep.
