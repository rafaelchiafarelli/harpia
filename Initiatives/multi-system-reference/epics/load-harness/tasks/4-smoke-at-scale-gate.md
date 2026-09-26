## Smoke-at-scale gate + server tuning notes

- **Depends on:** tasks 1–3; `db-concurrency` task 1.
- **Contract:** an opt-in script `Docker/run_multi_system_load.sh` (like
  `run_pg_tests.sh`: throwaway PostgreSQL, then `station`, then `spawn.py` with
  50 `edge` + 50 `handheld` JVM clients for 60s, then `report.py`). It passes
  when: zero crashed clients, zero rows lost (DB row count equals the
  successful `create` records), and zero errors other than the deliberately
  injected `guest` denials. **This proves the harness works. It is not a
  benchmark.**
  Plus a "Running at scale" section in the multi_system README: `station`
  tunables (pool size vs PostgreSQL `max_connections`, gRPC server thread
  count, session TTL vs re-issue storm, CURVE handshake cost at ramp) and
  what to watch in the report when raising N into the hundreds on real
  hardware.
- **Pre-work:** none.
- **Out of scope:** hundreds-scale runs in this environment (Rafael runs those
  elsewhere).
- **Tests:** the script passes; it is opt-in and not in the default suite
  (duration).
