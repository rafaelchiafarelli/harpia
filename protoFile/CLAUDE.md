# ProtoFile — emit `.proto` files per message and compile them to C++

**Pipeline role:** Stages ~1-7 (proto emission) + Stage 7 (protoc → `.pb.h/.cc`) + Stage 13 (gRPC stubs). Front-end stages hand `MessageCreator` message objects here; `FileCreator` turns each into `.proto` (+ sidecar) files; `ProtoCompiler`/`GrpcCompiler` shell out to `protoc`.
**Entry points (from main.py):**
- `FileCreator(message=msg, imports=imports, dest=testDestination)` → `.Process()` then `.save()`, called per message in a loop.
- `ProtoCompiler(dest).Process()` (Stage 7), `GrpcCompiler(dest).Process()` (Stage 13). Both return an `Error` (non-fatal) or `None`.
**Inputs → Outputs:** consumes message objects (`.name`, `.md5Hash`, `.variables`, `.dependency`, `.isEnum`, `.visibility`, `.tableName`, `.access_modifiers`). Emits under `<dest>/`: `proto/protofiles/<name>_<hash>.proto`, `proto/protofiles/<name>_<hash>_service.proto`, `modifier/…_modifier.message`, `access_modifier/…_access.variable`, `database/…_table.sql`, `database_access/…_encrypted.pswd`. Compilers read `<dest>/proto/protofiles/*.proto` and write `<dest>/generated/cpp/`.

## Files
- `FileCreator.py` — the core emitter. `Process()` builds the `.proto` text (syntax, imports, message/enum body, fields) and the service proto (via `readFromTemplate("Service.proto", …)`); `save()` writes all sidecar files via `Util.util.write_if_different` (skips the write, preserving mtime, when content is unchanged). Field emission: `map<K,V>` uses `v.typeMap` (NOT `v.type`, which the parser clobbers to the last primitive in the brackets); `repeated` prefix when a modifier is `REPETEABLE` (note spelling); `protoType()` maps primitive tokens (INT32/INT64/FLOAT/STRING) to proto names, else uses the composed type's name. Long comment block (lines ~88-113) is a design sketch of unimplemented access/CRUDL/callback protos. `save()` does NOT write `database/<name>_<hash>_table.sql` — `Database/SqlAdapter.py` (runs later in `main.py`, unconditionally, for every message) always supersedes it with the real schema; writing a stub here first just meant the file was touched twice on every run.
- `ProtoCompiler.py` — Stage 7. `shutil.which("protoc")`; if absent, logs and returns `PROTOC_NOT_FOUND` (non-fatal). Runs `protoc -I <dest>/proto --cpp_out <dest>/generated/cpp <all protos>`.
- `GrpcCompiler.py` — Stage 13. Needs both `protoc` and `grpc_cpp_plugin`. Globs `*_service.proto`, runs `protoc … --grpc_out … --plugin=protoc-gen-grpc=<plugin>`.
- `ProtoFileProcessor.py` — empty stub class (no logic).

## Key facts / gotchas
- **Filenames are md5-hash-qualified:** `{message.name}_{message.md5Hash}.proto`. The hash comes from the root `.harpia` file (`rootFile.getHash()`), so every message from one input file shares the same hash. Relevant to the upcoming multi-root feature: today all messages get one file hash; per-root hashing would change these names and the import paths below.
- **Import dedup:** `Process()` dedups `message.dependency` by target type name (`dep[1]`) via `seenDeps`, because protoc rejects importing the same file twice (a type referenced by both a singular and a repeated FK). Dependency imports are written as `import "protofiles/<dep>_<hash>.proto";` — same hash as the current message.
- The static `imports` list from main.py is passed in but is empty in practice; those become bare `import "…"` lines (note: no trailing `;` on that path, unlike the dependency path).
- Compilers are **non-fatal** by design: absent `protoc`/`grpc_cpp_plugin` (e.g. running on a bare host, not the Docker image) returns an `Error` that main.py just logs. Real generation happens inside the harpia Docker image (`docker/run.sh`).
- Both compilers use include root `-I <dest>/proto` so the `protofiles/<name>.proto` relative imports resolve and the layout is preserved in `generated/cpp/`.

## Touchpoints
- Called by: `main.py` (steps 6/7/13).
- Depends on: `Util.util.readFromTemplate` (Assets/proto templates, e.g. `Service.proto`), `Logger.logger`, `Errors.Error`, external `protoc`/`grpc_cpp_plugin`. Consumes message objects from `MessageCreator`. Static protos come from `Assets/proto/protofiles` (copied by main.py's `copyBasicProtos`).
