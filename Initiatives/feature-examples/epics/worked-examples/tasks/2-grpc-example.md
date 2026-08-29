## gRPC example

- **Depends on:** task 1 (fixture hash must be settled before pinning a
  README to it, same reason `HarpiaTest/app_example/consumer/README.md` already flags:
  "this example is pinned to HarpiaTest's hash").
- **Deliverable:** `HarpiaTest/app_example/grpc_demo/` — server + client over a real
  port (`grpc::CreateChannel`/`ServerBuilder`, not in-process), `users`
  message: `push` then `pullByID`, both with correct `x-user`/`x-pswd`
  metadata (`ClientContext::AddMetadata`). Mirrors `HarpiaTest/app_example/consumer`'s
  shape: `CMakeLists.txt` takes `-DHARPIA_GEN=<path>`, links
  `${GEN}/protofiles/users_<hash>_service.grpc.pb.cc` +
  `gRPC::grpc gRPC::grpc++`.
- **Tests:** build + run inside `Docker/run.sh`; README documents the
  exact expected stdout, same bar as `HarpiaTest/app_example/consumer/README.md`.

