## Spawner: hundreds of clients against one `station`

- **Depends on:** task 1; `reference-system` task 1 (bulk identities).
- **Contract:** `HarpiaTest/app_example/multi_system/load/spawn.py` (Python 3
  stdlib only, so it runs on the load machine without harpia's Docker image):
  `spawn.py --station host:port --edge-pub tcp://host:port --edges N
  --handhelds M [--emulators K] --ramp <s> --duration <s> --pki <dir> --out <dir>`.
  It assigns identities from the provisioned set (it fails fast if there are
  fewer identities than N+M), staggers starts over `--ramp` so TLS/CURVE
  handshakes don't all hit at once, restarts nothing (a crashed client is a
  result, recorded), stops everything on duration or Ctrl-C, and leaves one
  JSONL per client in `--out`. `--emulators K` is optional and drives the
  existing emulator script's `adb` path.
  It documents the host-side limits it checks and warns about before starting
  (`ulimit -n`, ephemeral ports, available RAM per JVM, `-Xmx` default for
  the handheld JVMs).
- **Pre-work:** none.
- **Out of scope:** distributing clients across several load machines (run
  `spawn.py` on each, with disjoint identity ranges via `--identity-offset`).
  That's documented, not automated.
- **Tests:** spawn 10 + 10 for 10s in Docker, then 20 JSONL files exist, a
  clean shutdown leaves no orphan processes, and too few identities fails
  before anything starts.
