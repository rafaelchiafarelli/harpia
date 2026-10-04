## CURVE encryption + ZAP client-key allowlist (hardened profiles)

- **Depends on:** task 1; `py-foundation` task 4.
- **Contract:**
  - CURVE:
    - `CurveServerKeys(secret_key)` for the bind side and
      `CurveClientKeys(server_public_key, public_key, secret_key)` for the
      connect side, as trailing optional factory arguments. Empty means
      plaintext, unchanged.
    - `generate_curve_keypair()` wraps `zmq.curve_keypair()`.
    - **`linger=0`** on every socket, so a failed handshake can't block
      close forever (the `ZmqAdapter/CLAUDE.md` gotcha).
  - `harpia_runtime/zap.py`, a port of `ZmqAdapter/runtime/harpia_zap.h`:
    - `AllowList.from_env()` reads `HARPIA_ZMQ_ALLOWLIST` in the **same
      format**: `<z85-key> <identity>` per line, blank lines skipped.
    - A line is a comment only when its first token starts with `#`
      **and** is not a valid 40-char Z85 key. `#` is a Z85 digit: this is
      the fixes/000005 bug, and Python must not reintroduce it. An
      identity token starting with `#` is ignored.
    - `ZapHandler`: a thread running a REP loop on
      `inproc://zeromq.zap.01`, answering `200`/`400`.
    - Fail-safe: no file / empty file denies every key. One value-free
      `zap_denied` record per rejection (z85 public key + identity only).
    - `ensure_running(ctx)` is idempotent per context. If the endpoint is
      already bound it becomes inert instead of raising.
  - Under `transport_hardening_required(compliance)`, bind-side CURVE
    sockets call `ensure_running(ctx)` before enabling `curve_server`.
    Non-hardened output is unchanged.
- **Watch for:** pyzmq ships `zmq.auth.ThreadAuthenticator`. It may be
  used only if the allowlist format, fail-safe default and audit behavior
  match exactly. Otherwise write the REP loop by hand. Record which.
- **Bar:** the same allowlist file and keys give the same accept/deny
  decisions for C++ and Python servers, including keys containing `#`.
- **Out of scope:** per-message ZMQ authorization beyond the allowlist (C++
  has none).
- **Tests:**
  - Mirroring `test_zmq_zap.py`: listed key accepted, unlisted denied,
    missing file denies all, comment lines, a key **starting with `#`**
    accepted, one audit per denial.
  - Plain CURVE round-trip; a wrong server key times out and never
    downgrades to plaintext.
  - A protoc+g++-gated Python-CURVE-client → C++-ZAP-server case.
