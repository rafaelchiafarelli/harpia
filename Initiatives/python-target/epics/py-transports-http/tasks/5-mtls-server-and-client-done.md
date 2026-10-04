## Fail-safe mTLS bring-up (gRPC + HTTP) + client helpers, incl. mixed mode

- **Depends on:** tasks 2–4.
- **Contract:**
  - `harpia_runtime/tls.py`:
    - `MtlsFiles(ca, cert, key)` with `complete()`, and `SecurityRefused`.
    - `grpc_server_credentials(hardening_required, files,
      client_cert_required=True)` uses `grpc.ssl_server_credentials(...,
      require_client_auth=...)`.
    - `http_server_context(hardening_required, files,
      client_cert_required=True)` uses `ssl.SSLContext` with
      `CERT_REQUIRED`, or `CERT_OPTIONAL` for mixed mode.
    - Client side: `grpc_channel_credentials(files)` and
      `http_client_context(files)`.
    - **Fail-safe:** hardening required + incomplete files → raises
      `SecurityRefused`. Never a silent plaintext server.
  - The bring-ups bake `HARDENING_REQUIRED` from
    `transport_hardening_required(compliance)`. When
    `Database.auth_gate.transport_mode()` diverges (a `protected`/`open`
    message), they also bake `EMIT_TLS`/`CLIENT_CERT_REQUIRED`. Otherwise
    they stay identical to a non-diverging project, the same rule as C++.
  - The client-cert CN is exposed to handlers: HTTP via
    `getpeercert()['subject']`, gRPC via
    `context.auth_context()['x509_common_name']`.
- **Bar:** the same PKI (`mtls_provision.sh`) works for C++ and Python
  peers in both directions.
- **Out of scope:** what is done with the CN (task 6).
- **Tests:** generated-project tests mirroring `test_grpc_mtls.py`,
  `test_rest_soap_mtls.py` and `test_mtls_optional_mode_spike.py`:
  - certless client refused under required mode;
  - CA-signed client accepted;
  - foreign-CA client refused;
  - mixed mode lets a certless client reach an `open` message but not a
    `protected` one;
  - incomplete files → `SecurityRefused`.
