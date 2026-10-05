## Public/private DB segregation registry

- **Depends on:** task 2a.
- **Contract:** `harpia_generated/db/registry.py`, a port of
  `DbRegistryAdapter`'s project-wide output:
  - `REGISTRY`, a tuple of `RegistryEntry(table, Visibility.PUBLIC|PRIVATE,
    owner_project)`, deduped by table name; a conflicting later declaration
    becomes a `# note:` comment, as in C++;
  - `PROJECT_NAME`, from `ComplianceContext.project`;
  - `db_access_check(requesting_project, table) -> AccessDecision`
    (`ALLOWED` / `DENIED_PRIVATE_CROSS_PROJECT` / `DENIED_UNKNOWN_TABLE`),
    plus the one-arg overload keyed off `PROJECT_NAME`.

  Self-contained (stdlib only), so a second project can import another
  project's registry module.
- **Bar:** same decisions as the C++ `db_access_check` for every fixture
  table, including the `users`/`top_users` conflict note.
- **Out of scope:** enforcing it inside DAOs (C++ doesn't either).
- **Tests:** golden snapshot of `registry.py`; unit tests of every decision
  branch; a cross-project import test.
