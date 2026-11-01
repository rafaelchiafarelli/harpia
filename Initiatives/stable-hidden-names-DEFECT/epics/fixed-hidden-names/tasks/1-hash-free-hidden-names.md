## Hidden fields get fixed names: HARPIA_ID / HARPIA_STATUS / HARPIA_ERROR / HARPIA_ORIGINATOR

- **Depends on:** nothing.
- **Contract:** every generated message's hidden fields are named
  `HARPIA_ID` (wire number 1, int32, primary key), `HARPIA_STATUS`,
  `HARPIA_ERROR`, `HARPIA_ORIGINATOR`, independent of the root file's text.
  The hidden-field recogniser is one prefix, `HARPIA_`, everywhere it is
  matched today (`ID_` / `STATUS_` / `ERROR_` / `ORIGINATOR`). A user field
  whose name normalises (lower-case, `_` removed — protoc's JSON-name rule) to
  a hidden name is a parse-time error.
- **1. Corroborate (red first):** `UnitTests/test_hidden_names.py` — generate
  the same Include module under two roots that differ only by an extra
  `import`; the `.proto` field names and the SQL column names of the shared
  message must be identical. Fails today (`ID_<hashA>` vs `ID_<hashB>`).
- **2. Fix:**
  - `Message/Variables.py` (`__init__`, `AddHiddenVariables`) — the names; the
    `ORIGINATOR` constant keeps the hash as its value.
  - recognisers: `Message/FieldMap.py`, `Database/model.py` (incl.
    `pk=v.name.startswith("ID_")`), `Util/util.py`, `PyTests/runtime/testing.py`,
    `JavaDatabase/JavaCrudlAdapter.py`, `PyDatabase/` (runtime + adapter),
    `PyGrpc/`, `TestAdapter/`, any other `ID_`/`STATUS_`/`ERROR_`/`ORIGINATOR`
    match found by grep.
  - reserved-name check in the front end (`Errors/Error.py` new type).
  - examples: `HarpiaTest/app_example/consumer/src/main.cpp`
    (`set_id_<hash>` → `set_harpia_id`), multi_system `Handheld.java`.
  - doc comments that say `ID_<hash>`.
- **3. Unit tests (kept):** the red test; a parse-error test for a user field
  named `harpia_id`; every test pinning `id_<HASH>` / `ID_<HASH>` accessors
  updated (the `HASH` constants stay — filenames keep the hash).
- **Golden move:** all of `UnitTests/golden*/` that mention hidden fields
  (proto, db, migrate, zmq, json/xml/yaml, Java, Python). Review: the diff must
  be names only.
- **Docs:** `harpia.process.md` stage 0, `USAGE.md` (§5, §16 caller-assigned
  key note), `Util/CLAUDE.md`, `Message/CLAUDE.md`.
- **Note:** after this task alone an old database still fails to migrate;
  tasks 2–3 add the rename. Don't merge the epic to `dev` before them.
