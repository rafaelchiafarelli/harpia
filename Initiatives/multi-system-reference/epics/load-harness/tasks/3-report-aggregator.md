## Report aggregator

- **Depends on:** task 1 (record format).
- **Contract:** `load/report.py <out_dir>` (stdlib only) prints and writes
  `summary.json` + `summary.md`: per client kind and per op: count, ok rate,
  ops/s, latency p50/p95/p99/max; errors grouped by gRPC code
  (`UNAVAILABLE`, `UNAUTHENTICATED`, `PERMISSION_DENIED`,
  `DEADLINE_EXCEEDED`, …); ZMQ sequence gaps per subscriber; a per-10s
  timeline so ramp-up and saturation are visible. No charts required; plain
  tables that diff well between runs.
- **Pre-work:** a small hand-written JSONL fixture set (committed with the
  test) covering every record type and an error mix.
- **Out of scope:** dashboards.
- **Tests:** the fixture set produces an exactly-expected `summary.json`.
