### Session J.17 — Confirm JeroMQ CURVE support

- **Depends on:** nothing (pure verification, can run any time).
- **Deliverable:** a confirmed answer, against a pinned JeroMQ version,
  to whether CURVE is actually supported — `../../README.md` §2 flags this
  as an unconfirmed claim, same discipline this repo applied to the
  SOCI::PostgreSQL alias question before assuming an answer. Blocks J.19,
  nothing else.
- **Tests:** the verification itself — a minimal CURVE handshake against
  the pinned JeroMQ version, pass/fail.

## Confirmed (2026-08-23): CURVE is supported

**Pinned version: `org.zeromq:jeromq:0.6.0`** (current latest release on
Maven Central as of this check).

Verified via web research (no live network egress from the harpia
generation host itself, and no local JeroMQ jar to hand in this
environment — a real handshake, per the test bar above, still needs to
run once a JDK lands in the Docker image; see the caveat below):

- **The security mechanism is real and has been for years, not a stub.**
  JeroMQ's own docs (`doc/security/curve.md`) describe the CURVE
  mechanism (RFC ZMTP 25) as implemented, backed by
  `zmq.io.mechanism.curve.Curve` in the source tree and a public
  `org.zeromq.ZMQ.Curve` javadoc entry across every recent release line
  (0.5.0/0.5.1/0.5.2 all publish it).
- **It's not a recent, undertested addition.** The `CHANGELOG.md` shows
  CURVE support arriving in 0.4.1 (2017, "now based off of 4.1.7 of
  libzmq... additional security features"), a real bug fix in 0.4.3
  ("CURVE keys were being parsed as strings", plus `ZAuth`/`ZCert`/
  `ZCertStore` added for managing CURVE certificates), a protocol-level
  fix in 0.5.1 ("encoding/decoding of the `COMMAND` flag when using CURVE
  encryption"), and a further authentication-logic fix in 0.5.3 (2022,
  "handle reversed client/server roles during connection establishment").
  Continuous maintenance attention across 5+ years, not a claim resting
  on one changelog line.
- **API surface exists and is documented with a working example**
  (a community gist, `Security.java`): `Socket.setCurveServer(boolean)`
  (the current name — `setAsServerCurve` is the deprecated predecessor),
  `setCurvePublicKey(byte[])`, `setCurveSecretKey(byte[])`,
  `setCurveServerKey(byte[])` (client-side, the server's public key), plus
  a `Curve` class for keypair generation.

**Not resolved here, deliberately deferred to J.19** (this session's
deliverable is confirmation only, not implementation): the exact key-
encoding handling (the example gist calls `.getBytes()` on a Z85-encoded
string where the setters more likely want raw 32-byte binary — looks like
either a simplified/imprecise example or a Z85-decode step the gist
omits) needs to be nailed down against the actual 0.6.0 API when J.19
writes real code, not guessed at here.

**Caveat, stated plainly:** this confirmation is web-research-based, not a
locally-executed handshake — this sandbox has no JDK/JeroMQ jar to run one
against (the same gap flagged throughout this thread's other gradle+JDK-
gated tests). J.19's own integration test is where a REAL handshake
finally runs, whenever a Java-capable environment executes it. If that
disagrees with this confirmation, J.19's own history file is the place to
correct the record, not silently patch over it.