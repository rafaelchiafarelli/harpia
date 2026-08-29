## SOAP example

- **Depends on:** task 1.
- **Deliverable:** `HarpiaTest/app_example/soap_demo/` — Crow-backed SOAP server
  (`harpia::soap::register_users_soap`) + a client posting raw SOAP
  envelopes (`set`/`get`/`update`/`delete`, credential in
  `<soap:Header><credentials>`), `users` message.
- **Tests:** build + run inside `Docker/run.sh`; demonstrate the 401
  Fault path (wrong credential) alongside the happy path.

