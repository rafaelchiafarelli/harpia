## `edge`: the Linux C++ program (no DB)

- **Depends on:** tasks 1–3.
- **Contract:** `HarpiaTest/app_example/multi_system/edge/`: a C++ program
  that:
  - connects to `station` (`--station host:port`) with
    `channel_credentials()` + its client cert, obtains a session
    (`heartBeat` + `harpia-issue-session`), then `create`s one `reading` every
    `--interval` ms,
  - binds a ZMQ PUB (`--pub tcp://*:port`) with CURVE server keys + the ZAP
    allowlist, publishing one `live_sample` per reading,
  - every `--notes-every` readings, `list`s `field_note`s from `station` and
    logs how many there are (so the "from the Windows machine" direction is
    exercised, not only writes),
  - exits cleanly on SIGINT.
  **No database is linked into this program.** That is a checked build
  property, not a convention.
- **Pre-work:** none.
- **Out of scope:** load mode (epic 4 task 1).
- **Tests:** in Docker, `station` + `edge` run for 5s. Readings land in the DB,
  and a test SUB with an allowlisted key receives `live_sample`s. The `edge`
  binary does not link SOCI (checked with `ldd`/link map).
