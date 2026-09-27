## Java gRPC mTLS channel helper (JVM + Android)

- **Depends on:** nothing. Server side already exists (C++ `GrpcServer` with
  `SslServerCredentials`, `Database/runtime/harpia_grpc_mtls.h`).
- **Contract:** a generated Java runtime class `com.harpia.runtime.HarpiaGrpcTls`
  (copied into every Java-target project, like `HarpiaZmq`) with
  `static io.grpc.ChannelCredentials credentials(InputStream caPem,
  InputStream clientCertPem, InputStream clientKeyPem)`, built on
  `io.grpc.TlsChannelCredentials` (transport-agnostic, so the **same**
  credentials object works with `grpc-netty-shaded` on the JVM and with
  `grpc-okhttp` on Android). Java counterpart of C++
  `harpia::grpc_transport::channel_credentials()`. Streams, not paths,
  because Android loads certs from assets/raw resources, not files.
- **Deliverable:** the runtime class plus its copy step in the Java pipeline;
  `project.gradle.tmpl` unchanged unless `TlsChannelCredentials` needs a newer
  grpc-java than 1.62.2 (it doesn't per grpc-java docs, but that's to be
  confirmed by compiling, not assumed).
- **Pre-work:** none; the PKI comes from the existing `mtls_provision.sh`.
- **Out of scope:** session tokens (task 2), Android on-device (task 4).
- **Tests:** a JDK-gated pytest (same gating as `test_java_zmq_curve.py`) that
  starts a hardened generated C++ `GrpcServer` and calls `heartBeat` from a
  Java client: no client cert → `UNAVAILABLE` (handshake refused); CA-signed
  client cert whose CN maps to `main` → OK; cert from a foreign CA → refused.
