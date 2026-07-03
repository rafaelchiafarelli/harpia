# Message — semantic model: turns a message/enum token block into a typed object with fields

**Pipeline role:** Front-end, stage ~2–3 (semantic analysis). Consumed by `MessageCreator` (LexicalAnalizer) to build the intermediate representation the back-end `FileCreator` renders into proto/C++.
**Entry points:**
- `Message(fileName, availableMessages, md5Hash).Process(tokens)` → `None` or `Error`; called by `MessageCreator.CreateMessages`.
- Internally `Message.Process` constructs `Variables(...)` or `EnumValues(...)` and calls their `.Process()` then `.get()`.
**Inputs → Outputs:** a slice of tokens for one `message {...}`/`enum {...}` block → a `Message` with `.name`, `.variables` (list of `variable` or `(name,int)` enum tuples), `.access_modifiers`, `.tableName`, `.visibility`, `.isEnum`, `.dependency`.

## Files
- `Message.py` — `Message`: scans the block. Reads access modifiers (tokens between the preceding NEWLINE and the `message` keyword) e.g. `pull`/`event`/`stream` → sets `isOneToMany`. Name = ID token after `message`/`enum`. Between `{` and `}` delegates to `Variables` (message) or `EnumValues` (enum). After `}`: a trailing `;` sets `visibility=PRIVATE`; a trailing ID sets `tableName`. `dependency` = composed-field type names.
- `Variables.py` — `variable` (POD: index, name, type tuple, regex, modifiers, typeMap, paginationSize, repeteableSize, constant) and `Variables` (the field parser). Splits fields on `;`, detects modifiers `repeteable[N]`/`optional`/`unique`/`required`/`pagination[N]`/`map<...>`, resolves type (scalar INT32/INT64/FLOAT/STRING, `map`, or a composed message name from `composedVariables`), and derives a validation regex. Assigns `index = len(variables)+1`.
- `EnumValues.py` — `EnumValues`: two passes. First collects explicit `NAME = N;` values, sorts them, computes next free value; second pass assigns auto values to bare `NAME;` entries. Enforces unique values via `allUnique()`. Accepts 2-token (`NAME;`) or 4-token (`NAME = N;`) forms; each value must start its line.

## Key facts / gotchas
- **md5 hash drives hidden field names.** `Variables.__init__` auto-prepends `ID_<md5>` and `AddHiddenVariables` appends `STATUS_<md5>`, `ERROR_<md5>`, and `ORIGINATOR` (named `ORIGINATOR_<md5>` only when `isOneToMany`). Because `main.py` passes the ROOT file's md5 for every message, all messages across all imported files share the same hash suffix — a collision risk for the upcoming multi-root-file feature (two roots ⇒ different hashes; same root imported twice ⇒ identical suffixes).
- Composed (message-typed) fields: if `var.type[1] in composedVariables`, regex is set to the type itself and the type name is added to `self.dependencies` (1-to-many via link table when `repeteable`).
- **Mutable class-attribute bug in `EnumValues`:** `values = []` is a class attribute and `createValues` appends to it, so enum values can leak across `EnumValues` instances. `Variables`/`Message` mostly re-init lists in `__init__` (safer), but `Message`'s class-level defaults (`variables=None` etc.) are shadowed per-instance.
- `type` is stored as the raw token tuple `(TYPE, lexeme, line, col)`; downstream code reads `var.type[0]`/`[1]`.
- Regex constants live on `Variables` (RegexForInt/Float/String); `map` regex via `RegexForMaps`.

## Touchpoints
- Called by: `LexicalAnalizer/MessageCreator.py`.
- Depends on: `Errors.Error`, `Logger.logger`, `uuid`. Consumed by back-end `FileCreator`.
