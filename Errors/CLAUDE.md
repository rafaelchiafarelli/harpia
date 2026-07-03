# Errors — uniform error object returned (not raised) throughout the pipeline

**Pipeline role:** Cross-cutting, all stages. Every stage returns an `Error` instance (or `None` for success) instead of raising; callers check `if result is not None`.
**Entry points:** `Error(errCl, errTp, FileName="", FileLine="", CharacterNumber=0)`; `.__str__()` for logging. Enums `Types` and `Classes` supply the codes.
**Inputs → Outputs:** construction args → a printable error carrying error class, type, file, line, char, plus the caller's source location.

## Files
- `Error.py` — three definitions:
  - `Types(Enum)` — ~39 specific error codes (lexical, brace/paren/bracket/comment count mismatches, import incomplete, malformed pagination/repeteable/map/enum, no name in message, regex not found, protoc/gRPC compilation failures, etc.).
  - `Classes(Enum)` — coarse category (FILE_HAS_ERROR, BRACES, MODIFIERS, VARTYPES, ENUMTYPES, MESSAGES, REGEX, PROTO_COMPILATION, ...).
  - `Error` — holds `errType`, `errClass`, `FileNme` (sic — misspelled attribute), `FileLine`, `CharacterNumber`. `__init__` uses `inspect.stack()[1]` to record the CALLER's filename+line into `self.outMsg`.

## Key facts / gotchas
- Errors are **returned, never raised** — the whole pipeline relies on `None`-vs-`Error` checks. Returning an `Error` up the call chain is how failures propagate.
- Attribute is `FileNme` (typo) not `FileName`; the constructor param is `FileName`. Match existing spelling when reading `.FileNme`.
- Duplicate enum value: `EXPECTING_A_INTEGER_CONST_VALUE = 29` and `NOT_VALID_ENUM = 29` share value 29 (aliased). Compare by `.name`, not value.
- `.__str__()` prepends the caller's source location captured at construction time via `inspect`.

## Touchpoints
- Called by: essentially every module (LexicalAnalizer, Message, back-end, main).
- Depends on: stdlib `enum`, `inspect` only.
