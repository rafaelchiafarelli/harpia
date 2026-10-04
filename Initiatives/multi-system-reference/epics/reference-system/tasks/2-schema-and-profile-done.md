## Reference schema + hardened compliance profile

- **Depends on:** nothing for writing the files. It's task 2 so it lands
  after task 1 on the branch.
- **Contract:** `HarpiaTest/app_example/multi_system/harpia/`: one root
  `.harpia` (+ `Include/` if needed) and a `project.harpia.yaml` that turns
  hardening on (`topology: cloud_connected`). Three messages, each with a
  one-line comment saying who writes it and who reads it:
  - `reading`: table message; `edge` creates, `station` stores, `handheld` lists.
  - `field_note`: table message; `handheld` creates/updates, `edge` reads.
  - `live_sample`: table-less, one-to-many ZMQ PUB/SUB; `edge` publishes,
    `handheld` subscribes.
  The exact modifier tokens are chosen from `USAGE.md` §3 and the
  `.harpia` authoring constraints (no bool, comment charset, etc.). Keep it
  small; this is an example, not a coverage fixture.
- **Deliverable:** the schema files, generated for **both** `cpp` and `java`
  in the task's own test (the example builds from generated output, nothing
  generated is committed), plus the RBAC roles the three programs use:
  `station` has no client role; `edge` = `main`; `handheld` = `main`; a
  `guest` identity exists only to prove denial.
- **Pre-work:** none.
- **Out of scope:** any program code.
- **Tests:** generation succeeds for both languages; generated gRPC services
  exist for `reading`/`field_note`; generated ZMQ PUB/SUB exists for
  `live_sample` in C++ and Java.
