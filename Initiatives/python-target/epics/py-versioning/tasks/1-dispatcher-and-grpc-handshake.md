## Shared capability dispatcher + gRPC capability handshake

- **Depends on:** `py-transports-http` task 4.
- **Contract:**
  - `harpia_runtime/capability/dispatch.py`, a port of
    `Capability/runtime/harpia_capability_dispatch.h`:
    `Dispatcher(fallback)`, where the fallback is **mandatory** (no
    default), `on(type, handler)` and `dispatch(type, peer_caps)`. It calls
    the handler only when the peer covers the type **and** a handler is
    registered; otherwise it calls the fallback.
  - The gRPC slice:
    - a generated `harpia_generated/capability/capabilities_<roothash>_grpc.py`
      servicer whose `GetCapabilities` returns the baked-in type list from
      `Capability.capability_common.message_type_names` (imported, not
      re-derived). It is ungated, like `heartBeat`. `GrpcServer` registers
      it.
    - `harpia_runtime/capability/grpc.py` with
      `negotiate(channel, timeout_s, on_legacy_peer=noop) -> set[str] | None`.
      Any non-OK status (UNIMPLEMENTED, DEADLINE_EXCEEDED, …) calls
      `on_legacy_peer()` once and returns `None`. It never hangs.
  - Filenames are root-hash-qualified, and `prune_stale_outputs`
    already whitelists `capabilities`.
- **Tests:** mirroring `test_message_versioning_capability.py`: the
  advertised set is correct, a legacy peer (service not registered) calls
  the fallback once, and the timeout is honoured. A protoc+g++-gated
  C++-client → Python-server negotiate.
