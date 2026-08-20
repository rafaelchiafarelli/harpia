# Util — shared, spec-agnostic helpers

**Pipeline role / purpose:** Grab-bag of small generic helpers used across the
generator. No pipeline stage of its own. Deliberately generic — per the file
header, feature/spec-specific logic should NOT live here.

**Entry points:** functions imported directly, e.g. `from Util.util import
loadTemplate, chooseDemo, copyCMakeFiles, ...`.

**Inputs → Outputs:** varies per function (paths, Message objects, strings).

## Files
- `util.py` — every helper below lives here.

## Public functions (in util.py)
- `write_if_different(path, content) -> bool` — writes `content` to `path`
  unless it's already there unchanged, so an unchanged generated file keeps
  its mtime (a downstream `cmake`/`make` build then correctly skips
  recompiling it, instead of every regenerate looking like "everything
  changed"). Used by every adapter that emits generated C++/SQL/proto text
  (`JsonAdapter`, `XmlAdapter`, `ZmqAdapter`, every `Database/*Adapter.py`,
  `ProtoFile/FileCreator.py`, `TestAdapter/TestAdapter.py`) in place of a raw
  `open(path,"w").write(content)`. The actual write goes through
  `_atomic_replace` (temp file in the same dir + `os.replace`), so a process
  killed mid-write can never leave a truncated file at `path` — see
  `plans/crash-interrupt-recovery.md`.
- `copy_if_different(src, dst) -> bool` — same idea via `filecmp.cmp`, for
  the static/vendored files that are copied rather than rendered
  (`copyCMakeFiles`, `copyBasicProtos`, `TestAdapter._vendor_deps`). Also
  routed through `_atomic_replace`.
- `_atomic_replace(dst, populate)` (private) — crash-safety primitive behind
  both of the above: builds new content into a same-directory temp file via
  `populate(tmp_path)`, then `os.replace(tmp, dst)` (atomic rename). On any
  exception the temp file is removed and the exception re-raised; `dst` is
  untouched until the rename succeeds.
- `prune_stale_outputs(dest, current_hash, valid_names)` — removes generated
  files left behind by a message renamed/removed since the last run, or by a
  previous run against a different root-file hash. Matches harpia's
  `<name>_<hash>...` filename convention (`_NAME_HASH_RE`) so it never
  touches anything that doesn't look generated (CMakeLists.txt, vendored
  `third_party/`, ...); `_ALWAYS_VALID_BASENAMES` allowlists the one
  non-message-keyed exception (`TestAdapter`'s `app_<hash>_test.cpp`).
  Called once by `main.py`, right after messages are parsed and before
  anything is written, replacing the old blanket `shutil.rmtree(dest)`.
- `chooseDemo(messages)` — picks the message that drives the end-to-end demo:
  the first non-enum message with a PUSH or PULL access modifier (client PUSHes,
  server PULLs). Returns a substitution dict `{DEMO_MESSAGE, DEMO_HASH,
  DEMO_SAMPLE_JSON}` or `None` if none qualify. `main.py` and `run_pipeline.py`
  pass the result into `copyServerClientTemplates`.
- `_sampleJson(msg)` (private) — minimal valid JSON payload: first plain scalar
  user field (skips hidden `ID_/STATUS_/ERROR_/ORIGINATOR` prefixes, maps, and
  composed/message refs) set to a demo value ("harpia-demo" or 7); else `"{}"`.
- `copyCMakeFiles(src, dest)` — copies the four `CMakeLists.txt` (root, `proto/`,
  `server_template`→`server/`, `client_template`→`client/`) from `src` into the
  build tree, creating dirs and removing any stale copy first. Also copies
  `Assets/vcpkg.json` → `<dest>/vcpkg.json` (Windows-only manifest; harmless
  no-op input on the Linux/Docker path, which doesn't look for it).
- `copyServerClientTemplates(src, dest, demo=None)` — writes `server/src/main.cpp`
  and `client/src/main.cpp` from the `*_template/src/main.cpp` sources, doing
  `%KEY%` placeholder substitution from the `demo` dict (via `_emitTemplate`). If
  `demo is None` (no push/pull message) it emits a tiny stub main that still
  compiles.
- `_emitTemplate(srcPath, destPath, demo)` (private) — does the `%KEY%` replace,
  or the stub if `demo is None`.
- `copyBasicProtos(src, dest)` — copies the always-needed `errorCode.proto` and
  `heartBeat.proto` into `dest/proto/protofiles`.
- `loadTemplate(callerFile, name)` — reads a code-gen template from the
  `templates/` dir next to the *calling* module (`os.path.dirname(callerFile)`).
  Templates use `str.format` placeholders; C++ braces must be escaped `{{ }}`.
  Used by adapters (e.g. TestAdapter) to load their `.tmpl` files.
- `isFileInFolders(folders, file)` — searches `folders` in order for `file`.
  Returns `(True, fullPath)` on hit, else `(False, Error(...))` (FILE_HAS_ERROR /
  IMPORT_INCOMPLETE_ERROR). Used by `pre_lex` for include resolution. NOTE for the
  multi-root feature: this is where the folder list is walked and joined
  (`"{}/{}".format(folder, file)`); currently returns a hard error the moment any
  folder in the list is missing.
- `isascii(s)` — returns `(bool, count)`: whether all chars are ASCII; on a
  non-ascii byte-length mismatch it returns the index of the first non-ascii-
  letter char. Used by `pre_lex`.
- `copyTemplates(src, dest)` — recursive copy of a whole tree, copying a file only
  if missing or the source is >1s newer (mtime check).
- `readFromTemplate(templateName, messageName)` — reads
  `./Assets/proto/protofiles/<templateName>` and substitutes `%USER_MESSAGE%`.
- `switch` — tiny class implementing a `switch`/`case` idiom (`switch(x)` +
  `switch.case(a, b)`).

## Key facts / gotchas
- Hidden-field prefixes: `_HIDDEN_PREFIXES = ("ID_","STATUS_","ERROR_","ORIGINATOR")`.
- Demo scalar types: `_DEMO_SCALARS = {"STRING","INT32","INT64","FLOAT"}`.
- Many copy helpers `os.remove` an existing destination before copying — path
  layout (server/client/proto subdirs of `dest`) is assumed throughout.

## Touchpoints
- Imported by: `main.py` (copyCMakeFiles, copyServerClientTemplates,
  copyBasicProtos, chooseDemo, prune_stale_outputs), `LexicalAnalizer/pre_lex.py`
  (isFileInFolders, isascii), every adapter that writes output
  (write_if_different / copy_if_different, plus loadTemplate), `tests/run_pipeline.py`.
- Depends on: `Errors.Error` (Error, Types, Classes), stdlib (shutil, os, re,
  filecmp, string, json, hashlib).
