## Cross-language: embed presence survives C++ ⇄ Python

- **Depends on:** tasks 1-2.
- **Deliverable:** `test_db_xlang3.py` gains an embed-presence check
  (`data.val` unset / all-default, `journey.path` nested) for C++ and Python
  writers and readers, SQLite + PG. Test only, unless a pair disagrees.
