# PyCapability — the Python target's capability handshake (message-versioning S5)

**Pipeline role / purpose:** python-target / py-versioning. The Python side
of `Capability/` + `GrpcCapabilityAdapter` (+ HTTP / ZMQ from task 2). A
stage of `LangBackend/python.py`'s `run_python`, before `PyGrpcAdapter`
(whose `GrpcServer` registers the generated servicer).

**Entry point:** `PyCapabilityAdapter(messages, dest, rootHash,
compliance).Process()` → `None`. Whole-project artifact (one advertisement
regardless of message count), like C++.

## Runtimes (copied under `harpia_runtime.capability`)
- `runtime/dispatch.py` → `.dispatch`: `Dispatcher(fallback)` (fallback
  mandatory, no default), `on(type, handler)`, `dispatch(type, peer_caps)` —
  handler only when the peer covers the type AND one is registered, else the
  fallback. Port of `harpia_capability_dispatch.h`.
- `runtime/grpc.py` → `.grpc`: `negotiate(channel, timeout_s,
  on_legacy_peer=noop) -> set[str] | None`; any `grpc.RpcError`
  (UNIMPLEMENTED, DEADLINE_EXCEEDED, UNAVAILABLE, …) → `on_legacy_peer()`
  once + `None`. Port of `harpia_capability.h`.
- `runtime/http.py` → `.http` (task 2): `negotiate(host, port, base,
  timeout_s, on_legacy_peer)` — `http.client` GET `<base>/capabilities`
  (timeout on connect + each read); refused / timeout / non-200 / bad JSON
  → legacy. Port of `harpia_http_capability.h`.
- `runtime/zmq.py` → `.zmq` (task 2): `negotiate(ctx, endpoint, timeout_s,
  on_legacy_peer)` — fresh REQ per call, `RCVTIMEO`, `linger=0`; any
  `ZMQError` / undecodable reply → legacy. Port of `harpia_zmq_capability.h`.

## Generated
- `harpia_generated/capability/capabilities_<roothash>_grpc.py`:
  `MESSAGE_TYPES` (= `Capability.capability_common.message_type_names`,
  imported — the C++ `kTypes` list), `capabilities_Service`
  (`GetCapabilities`, ungated), `add_to_server(server)`.
- `capabilities_<roothash>_http.py` (task 2; only when a table-bearing
  message exists — the route lives on `harpia_runtime.http.router`):
  `register_capabilities(router, base="")` → `GET <base>/capabilities`,
  body `to_json(capabilities_Response)` = `{"messageTypes":[…]}` (C++
  `MessageToJsonString`, byte-identical), ungated. `PyHttpAdapter(…,
  rootHash=…)` makes `HttpServer` register it under `rest_base` (C++'s
  bring-up doesn't — same additive divergence as gRPC, item 37).
- `capabilities_<roothash>_zmq.py` (task 2): `CapabilitiesResponder(ctx,
  endpoint)` (REP bind; `serve_once()` — caller owns the loop; `close()`).
- `PyGrpcAdapter(…, rootHash=…)` makes the generated `GrpcServer` register
  it. **Divergence from C++ (additive):** the C++ `GrpcServer` doesn't
  register `capabilities_service`; the Python task contract asks for it.

## Touchpoints
- Depends on: `capabilities_service_pb2` / `_pb2_grpc` (`PyAdapter` copies
  the framework proto), `Capability.capability_common`.
- Tested by: `UnitTests/test_py_capability.py` (one C++ peer binary over
  the generated `capability/` headers: http/zmq client + server modes).
