## gRPC servicers per message + `GrpcServer` bring-up (flat gate)

- **Depends on:** task 1; `py-foundation` task 2 (`_pb2_grpc.py`).
- **Contract:**
  - Generated `harpia_generated/grpc/<name>_<hash>_grpc.py`: a concrete
    `<name>_Service` servicer.
    - `push` → create; `pullByID` → read; `streamSrc` → list, paginated by
      the request's `offset`/`limit` when `limit > 0`. The connection is
      given back **before** rows are streamed out, as in C++.
    - `heartBeat` → echo.
    - Each data RPC borrows one pooled connection after the auth guard:
      `PoolExhausted` → `RESOURCE_EXHAUSTED` "db pool exhausted",
      reconnect failure → `UNAVAILABLE` "db reconnect failed".
    - Flat gate: `x-user`/`x-pswd` metadata, else `UNAUTHENTICATED`.
      `heartBeat` is never gated.
  - Generated `harpia_generated/grpc/grpc_server_bringup.py`:
    `GrpcServer(pool, address, max_workers)` registers every servicer on
    one `grpc.server(ThreadPoolExecutor)`, with `start()`/`stop(grace)`.
- **Bar:** the C++ gRPC client stubs and the Python servicers interoperate
  (same `.proto`, same metadata keys, same status codes).
- **Out of scope:** mTLS (5), RBAC/sessions (6–7), capability service
  (`py-versioning`).
- **Tests:**
  - Generated-project server test per RPC under the flat profile;
    `UNAUTHENTICATED` without metadata; `RESOURCE_EXHAUSTED` with a held
    pool of 1.
  - A protoc+g++-gated case: a C++ client calls `push`/`pullByID` on the
    Python server.
