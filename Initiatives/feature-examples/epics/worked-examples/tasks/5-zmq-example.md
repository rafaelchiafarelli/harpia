## ZMQ example

- **Depends on:** task 1.
- **Deliverable:** `HarpiaTest/app_example/zmq_demo/` — explicit standalone PUSH/PULL
  demo, reusing `courier` (already exists specifically for this: push-only,
  exercises the per-instance runtime origin id). README states plainly
  this is for discoverability/clarity, not a replacement for
  `Assets/server_template`/`client_template` (already a generic version
  of the same thing, copied into every generated project).
- **Tests:** build + run inside `Docker/run.sh`, confirm the message
  crosses and the origin id is stamped.

