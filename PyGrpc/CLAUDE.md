# PyGrpc — the Python target's gRPC servicers

**Pipeline role / purpose:** python-target / py-transports-http. The Python
side of the C++ `grpc/<name>_<hash>_grpc.h` services + `grpc_server_bringup.h`.
A stage of `LangBackend/python.py`'s `run_python`, after `PyHttpAdapter`.

**Entry point:** `PyGrpcAdapter(messages, dest, compliance).Process()` →
`None` (nothing without table-bearing messages).

## Runtime (`runtime/grpc_service.py` → `harpia_runtime.grpc_service`)
`CrudServicer(pool)` with class attributes `DAO`, `WRAPPER`
(`<name>_Message`), `ERROR_CODE` (`errorCode`), `GATE`; methods `push`
(`errorCode 0 "ok"` / `1 "create failed"`, status OK), `pullByID`
(`NOT_FOUND "not found"`), `streamSrc` (rows read, connection returned,
then streamed; `limit > 0` pages; `INTERNAL "list failed"`), `heartBeat`
(echo, never gated). Gate first, then one pooled connection:
`RESOURCE_EXHAUSTED "db pool exhausted"` / `UNAVAILABLE "db reconnect
failed"`. `Gate` returns `None` or `(StatusCode, details)`; `flat_gate`
checks `x-user` / `x-pswd` metadata (`UNAUTHENTICATED "unauthorized"`);
`metadata(context, key)`.

## Generated (`harpia_generated/grpc/`)
- `<name>_<hash>_grpc.py` per table-bearing message (= the C++
  `grpc/*_grpc.h` set): `class <name>_Service(CrudServicer)` +
  `add_to_server(servicer, server)` (wraps protoc's
  `add_<name>_ServiceServicer_to_server`).
  `GATE` is `harpia_runtime.rbac_gates.grpc_rbac_gate(name)` when
  `Database.auth_gate.effective_rbac` says RBAC (task 6), else `flat_gate`.
- `grpc_server_bringup.py`: `GrpcServer(pool, address="127.0.0.1:0",
  max_workers=10, mtls=None)` — every servicer on one `grpc.server(ThreadPoolExecutor)`,
  `port`, `start()`, `stop(grace=None)`; `SERVICES`; same
  `HARDENING_REQUIRED` / `EMIT_TLS` / `CLIENT_CERT_REQUIRED` baking as the
  HTTP bring-up (`harpia_runtime.tls.grpc_server_credentials`, secure port
  when TLS, `SecurityRefused` on incomplete files).

## Key facts / gotchas
- The servicer subclasses the typed runtime class, not protoc's untyped
  `<name>_ServiceServicer` (mypy `--strict` forbids subclassing `Any`);
  registration only looks methods up by name, so this is equivalent.
  The one call into protoc's untyped `add_*_to_server` carries a scoped
  `# type: ignore[no-untyped-call]`.
- `errorCode` is imported from its submodule
  (`harpia_generated.protofiles.errorCode_pb2`) so the import block sorts
  the same for every message name.
- Same `.proto`, metadata keys and status codes as C++: a C++ client built
  from the generated stubs calls the Python server unchanged.

- **RBAC over gRPC needs client certificates *required*** (task 6): in
  mixed mode (`CLIENT_CERT_REQUIRED = False`, which the HarpiaTest fixture's
  `open` message forces) grpcio never requests a client cert, so every
  RBAC-gated RPC of the generated `GrpcServer` answers `UNAUTHENTICATED`
  (fail-closed; the `open` message still works). C++ can request-and-verify
  there; Python can't (logged decision 33/34). The (role, op) matrix is
  tested on a required-cert server.

## Touchpoints
- Depends on: protoc's `_pb2` / `_pb2_grpc` (`PyAdapter`), the DAOs,
  `harpia_runtime.db.pool`.
- Tested by: `UnitTests/test_py_grpc.py`, `test_py_mtls.py`,
  `test_py_rbac.py`.
