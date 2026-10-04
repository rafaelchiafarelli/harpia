## DAO OnChange: publish on create/update + `phi_event_onchange` audit

- **Depends on:** task 1; `py-database` task 2a; `py-crypto-phi` task 4
  (for the phi DAO's `audit_sink`).
- **Contract:** for a table-bearing `event` message, the generated DAO
  calls `<name>_channel().publish(msg)` at the end of a successful
  `create()` and `update()`, and **never** in `read`/`list`/`remove`. A
  message that is both `event` and phi-bearing additionally records
  `("phi_event_onchange", "<table>", "<phi cols>")` right after the
  publish, reusing the DAO's `audit_sink`. Non-event DAOs and phi
  non-event DAOs are unchanged.
- **Out of scope:** cross-process events (ZMQ/DDS cover that).
- **Tests:**
  - Generated-project: create/update fire exactly one callback each;
    read/list/remove fire none.
  - The phi+event message records `phi_event_onchange` once per change,
    with no value.
  - Golden diff limited to event messages' DAOs.
