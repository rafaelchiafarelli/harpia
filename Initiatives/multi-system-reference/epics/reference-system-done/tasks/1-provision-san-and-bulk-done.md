## Dev PKI: extra server SANs + bulk client identities

- **Depends on:** nothing (can start alongside epics 1 and 2).
- **Contract:** `Assets/cmake/mtls_provision.sh` gains, **additively** (current
  positional usage unchanged):
  - `--san <dns-or-ip>` (repeatable): extra server SANs beyond
    `<server_CN>, localhost, 127.0.0.1`, so a Windows host reached by LAN IP or
    hostname (and `10.0.2.2` from the emulator) verifies.
  - `--clients-file <path>`: one `<identity> <role>` per line. Issues one client
    cert per identity and also writes a ready-to-use `rbac_map.txt`
    (`HARPIA_RBAC_MAP` format).
  - A companion `zmq_curve_provision.sh <out_dir> --clients-file <path>` (new
    or extended, whichever already exists) that writes one CURVE keypair per
    identity plus `zmq_allowlist.txt` (`HARPIA_ZMQ_ALLOWLIST` format).
  Sized for thousands of identities: no interactive prompts, idempotent re-runs
  (existing identities are kept, not re-issued).
- **Pre-work:** none.
- **Out of scope:** production PKI, cert revocation lists.
- **Tests:** SAN present in the issued server cert (`openssl x509 -text`); 500
  identities issued in one run, with `rbac_map.txt`/`zmq_allowlist.txt` line
  counts and formats checked; a re-run doesn't re-key existing identities; the
  existing mTLS tests still pass unchanged.
