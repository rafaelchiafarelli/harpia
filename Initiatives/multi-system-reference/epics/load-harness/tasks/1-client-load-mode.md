## Load mode in `edge` and `handheld-core`

- **Depends on:** epic `reference-system`.
- **Contract:** both clients gain `--load` with `--identity <name>`,
  `--rate <ops/s>`, `--duration <s>`, `--mix create:list:update`
  (weights), `--report <path.jsonl>`. In load mode each process is **one
  identity** (own cert, own CURVE key, own session), so the server sees N real
  distinct clients, not one client multiplexed. Each operation writes one JSONL
  record: `{t, client_kind, identity, op, ok, grpc_code, latency_us}`. ZMQ
  receive-side records `{t, identity, op:"sub_recv", seq_gap}` so dropped
  samples are visible.
  `handheld-core` load mode is reachable from `cli`, and from `app` via an
  intent extra, so emulators can join a run.
- **Pre-work:** none.
- **Out of scope:** spawning (task 2), aggregation (task 3).
- **Tests:** each client in load mode for 5s at 20 ops/s against `station`
  writes a well-formed JSONL whose op count is within 10% of rate×duration.
