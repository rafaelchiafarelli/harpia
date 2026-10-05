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

## Generated
- `harpia_generated/capability/capabilities_<roothash>_grpc.py`:
  `MESSAGE_TYPES` (= `Capability.capability_common.message_type_names`,
  imported — the C++ `kTypes` list), `capabilities_Service`
  (`GetCapabilities`, ungated), `add_to_server(server)`.
- `PyGrpcAdapter(…, rootHash=…)` makes the generated `GrpcServer` register
  it. **Divergence from C++ (additive):** the C++ `GrpcServer` doesn't
  register `capabilities_service`; the Python task contract asks for it.

## Touchpoints
- Depends on: `capabilities_service_pb2` / `_pb2_grpc` (`PyAdapter` copies
  the framework proto), `Capability.capability_common`.
- Tested by: `UnitTests/test_py_capability.py`.
