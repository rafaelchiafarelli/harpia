# edge -- the Linux program (C++, no database)

Writes readings to `station` over hardened gRPC and publishes a live stream
over CURVE ZMQ. It links **no** database library; the test checks that with
`ldd`. See `../README.md` for the whole system.

```sh
cmake -S HarpiaTest/app_example/multi_system/edge -B build/edge -DHARPIA_GEN=$PWD/build/ms_gen
cmake --build build/edge
HARPIA_ZMQ_ALLOWLIST=zmq/allowlist.txt \
  build/edge/edge --station station.lan:50051 --certs pki --identity edge \
                  --pub tcp://*:5556 --zmq-keys zmq --interval 500 --notes-every 10
```

| Flag | Default | Meaning |
|---|---|---|
| `--station` | `127.0.0.1:50051` | station's gRPC address |
| `--authority` | the station host | TLS name to verify station's certificate against (when you dial an address that isn't in its SAN) |
| `--certs` / `--identity` | `.` / `edge` | `ca.pem` + `client_<identity>.pem` / `_key.pem` |
| `--pub` | `tcp://*:5556` | where the `live_sample` PUB binds |
| `--zmq-keys` | `.` | directory with `zmq_server_secret.key` (edge is the CURVE server) |
| `--device` | `edge-1` | `device_id` written into readings and samples |
| `--interval` | 500 | ms between readings |
| `--notes-every` | 10 | list station's field notes every N readings (0 = never) |
| `--id-base` | 1 | first `reading` primary key (keys are caller-assigned; give each edge its own range) |
| `--count` / `--duration` | 0 / 0 | stop after N readings / S seconds (0 = until Ctrl-C) |

Each reading also goes out as one `live_sample`. Only subscribers whose
public key is in `HARPIA_ZMQ_ALLOWLIST` get through the CURVE handshake; with
no allowlist, every subscriber is refused (fail-safe). If station refuses the
bearer token (expired or revoked), edge re-issues it once and retries.
Final line:

```
edge: done readings_created=90 readings_failed=0 samples_published=90 sessions_reissued=0
```
