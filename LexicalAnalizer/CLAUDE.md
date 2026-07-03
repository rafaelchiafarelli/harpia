# LexicalAnalizer — front-end: pre-check, tokenize, and split a `.harpia` file into Messages

**Pipeline role:** Front-end, stages 0–2. Runs first: `pre_lex` (stage 0 pre-process/import discovery + md5), `LexicalAnalyzer` (stage 1 tokenize + comment/import stripping), `MessageCreator` (stage 2 group tokens into `Message` objects). Feeds the back-end `FileCreator`.
**Entry points (all called by `main.py`):**
- `pre_lex(folders, file, dest, includeFolder).process()` → returns `None` or an `Error`; then `.getListOfHarpias()`, `.getHash()`, `.getFile()`.
- `LexicalAnalyzer().process(fileName)` then `.CommentRemover()`, `.ImportRemover()`, `.getTokens()`.
- `MessageCreator(filename, tokens, md5Hash).CreateMessages(beginToken=0)` → `None`/`Error`; results in `.messages` (list of `Message`).
**Inputs → Outputs:** a `.harpia` source file → list of token tuples `(type, lexeme, line, col)` → list of `Message` objects.

## Files
- `pre_lex.py` — `pre_lex`: reads the file line-by-line; validates ASCII, trailing newline, and balanced `() {} [] /* */`; discovers `import "x.harpia";` lines and resolves each via `Util.util.isFileInFolders` into `self.listOfHarpiaImports` (absolute paths). Creates all output subdirs under `dest` (proto/protofiles, modifier, access_modifier, database, database_access). Computes `md5hash = hashlib.md5(all_data).hexdigest()` over the WHOLE file text.
- `LexicalAnalyzer.py` — `LexicalAnalyzer`: regex rule table → `tokenize()` (one `re.finditer` per line); `process()` opens/reads the file; `CommentRemover()` deletes `//` and `/* */` token spans; `ImportRemover()`/`parseImport()` strip `import ... ` token runs (redundant with pre_lex, which already handled imports as files).
- `MessageCreator.py` — `MessageCreator`: walks tokens tracking NEWLINE/LBRACE/RBRACE to carve out each `message`/`enum` block; recurses (`isInternal`) for nested defs; builds a `Message` per block, tracks `availableMessages` (names seen so far, used for composed-field resolution), enforces uniqueness via `allUnique()`.
- `Remover.py` — empty/stub (0 lines). Not used.

## Key facts / gotchas
- **Shared mutable class state (critical):** `LexicalAnalyzer.tokens`, `lin_num`, and `log` are CLASS attributes, so every `LexicalAnalyzer()` instance shares ONE token list. That is why `main.py` can append only the last include's `analizer.getTokens()` yet still get all files' tokens. Any multi-root-file work must account for this global accumulation (or make `tokens` instance-level).
- **md5 hash is per-file but only the ROOT file's hash is used everywhere:** `main.py` passes `rootFile.getHash()` as the single `md5Hash` to `MessageCreator`, so messages from imported files still get the root file's hash. Hash uniquifies hidden field names (ID_/STATUS_/ERROR_/ORIGINATOR_) — see Message/CLAUDE.md.
- Import resolution search path (in `pre_lex.__init__`): cwd, then `dirname(file)`, then the `includeFolder` arg (from `HARPIA_INCLUDE_FOLDER`).
- Rule ordering quirk: `INT32 r'int'` precedes `INT64 r'int64'`; `int64` lexes as `int` + `64`. Type detection relies on lexeme text, not just this.
- `MISMATCH` token → `LEXICAL_ANALYZER_ERROR`. Files must end in a newline (checked by pre_lex).

## Touchpoints
- Called by: `main.py`.
- Depends on: `Logger.logger`, `Errors.Error`, `Util.util` (isascii, isFileInFolders), `Message.Message` (MessageCreator builds these).
