## `handheld`: plain-Java core + Android app + JVM CLI

- **Depends on:** tasks 1–4; epic `java-hardened-client` (all tasks).
- **Contract:** `HarpiaTest/app_example/multi_system/handheld/`, a Gradle
  multi-module build:
  - `core/`: plain Java library, **no Android APIs**. Class `Handheld` with
    `start(Config)` / `stop()`. It opens an mTLS channel to `station`
    (`HarpiaGrpcTls` + `HarpiaSession`), subscribes to `edge`'s `live_sample`
    (JeroMQ + CURVE), creates one `field_note` per N samples received, and
    periodically `list`s `reading`s from `station`. All I/O goes through `Config`
    (streams for certs/keys, host:port strings), so the same code runs on both
    platforms.
  - `cli/`: JVM `main` wrapping `core` (flags mirror `edge`'s).
  - `app/`: thin Android app; one activity that starts `core` with certs from
    `res/raw` and shows counters (samples received, notes written, readings
    listed, last error). No business logic in `app/`.
- **Pre-work:** none.
- **Out of scope:** load mode (epic 4 task 1); UI polish.
- **Tests:** `cli` runs against `station` + `edge` in Docker for 5s with
  non-zero counters in all three directions. `app` builds (APK assembles);
  the on-device run is task 6.
