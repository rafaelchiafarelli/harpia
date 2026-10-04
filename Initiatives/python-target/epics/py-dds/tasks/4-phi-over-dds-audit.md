## phi-over-DDS publish audit

- **Depends on:** task 1; `py-foundation` task 4.
- **Contract:** a `dds` message with ≥1 phi field gets a publisher taking
  `audit_sink=default_audit_sink()`. Every `publish()` records exactly one
  `("phi_publish", <topic>, <phi field names>)` **after** the write. The
  subscriber is untouched (no `phi_receive`, same as C++). A non-phi `dds`
  message's module has no audit parameter at all.
- **Tests:** mirroring `test_dds_phi_audit.py`: N publishes give N
  value-free records; the non-phi output is unchanged.
