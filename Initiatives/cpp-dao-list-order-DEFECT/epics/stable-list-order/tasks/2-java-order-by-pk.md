## Java DAO list SELECT orders by the primary key (verify first)

- **Depends on:** nothing in code; run after task 1 so goldens move one task
  at a time.
- **First:** confirm whether `JavaDatabase/JavaCrudlAdapter.py:113`
  (`select_all_sql`) backs a list / paginated list without ORDER BY. If Java
  already orders (or pages differently), mark this task done with that finding
  and no code change.
- **Deliverable (if affected):** append ` ORDER BY "<id_col>"` to the list
  SELECTs; regenerate `UnitTests/golden_java/` and review.
- **Tests:** the Java PG CRUDL test (`test_java_db_crudl_postgres.py`) gains
  the same perturb-then-page assertion as task 1.
