## HTTP + ZMQ capability handshake slices

- **Depends on:** task 1; `py-transports-http` task 2; `py-zmq` task 1.
- **Contract:**
  - HTTP: `GET <base>/capabilities`, registered by `HttpServer` (one route
    shared by REST and SOAP, as in C++). It returns `capabilities_Response`
    as protobuf JSON and is ungated.
    `harpia_runtime/capability/http.py` provides
    `negotiate(host, port, base, timeout_s, on_legacy_peer)` over
    `http.client` with a real connect+read timeout. Any failure is treated
    as a legacy peer.
  - ZMQ: a generated `capabilities_<roothash>_zmq.py` `CapabilitiesResponder`
    (a REP socket; `serve_once()`, with the caller owning the loop).
    `harpia_runtime/capability/zmq.py` provides
    `negotiate(ctx, endpoint, timeout_s, on_legacy_peer)`: a fresh REQ
    socket per call, `RCVTIMEO`, `linger=0`, and any failure means a
    legacy peer.
- **Bar:** a C++ client negotiates with a Python peer, and the reverse,
  on both transports. Same wire messages, so this should hold by
  construction; the tests prove it.
- **Tests:** mirroring `test_message_versioning_capability_http.py` and
  `test_message_versioning_capability_zmq.py` (real round-trip; a closed
  tcp port is a legacy peer). A g++-gated cross-language case per
  transport.
