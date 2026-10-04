## End-to-end gate (Linux/Docker + emulator) + deployment README

- **Depends on:** tasks 1–5.
- **Contract:** two deliverables:
  - `UnitTests/test_multi_system_example.py` (same guard style as
    `test_consumer_fanout_example.py`): generates, builds all three programs,
    provisions PKI, starts `station` (PostgreSQL via the `run_pg_tests.sh`
    pattern; SQLite fallback in the default suite) + `edge` + 2 `handheld`
    CLIs, and asserts all flows. It also runs the negatives: a `guest`
    identity is denied `create`, and an un-allowlisted ZMQ key receives nothing.
    A second, emulator-gated entry (through
    `Docker/run_android_emulator_tests.sh`) runs the real Android `app` in
    place of one CLI.
  - `HarpiaTest/app_example/multi_system/README.md`: topology diagram, which
    identity/role each program uses, ports + firewall rules, how to copy the
    PKI to each machine, and step-by-step deployment on **real** Windows
    (`station`), Linux (`edge`) and an Android device (`handheld`). It has an
    "expected output" block per program, like `app_example/consumer`.
- **Pre-work:** none.
- **Out of scope:** load (epic 4); running it on real Windows (epic 5).
- **Tests:** the new test passes in the full Docker suite; the emulator entry
  passes via the emulator script.
