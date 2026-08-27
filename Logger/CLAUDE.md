# Logger — thin console logging wrapper used by every module

**Pipeline role:** Cross-cutting utility, all stages. No pipeline logic.
**Entry points:** `logger(outFile, moduleName)`; `.print(msg)`. Instantiated as a class attribute in most modules, e.g. `log = logger(outFile=None, moduleName="Message")`.
**Inputs → Outputs:** a message string → formatted line printed to stdout `"[<moduleName>]: line:<callerLine> - <msg>"`.

## Files
- `logger.py` — `logger`: stores `moduleName` and `outFile`. `.print()` uses `inspect.stack()[1]` to prefix the caller's line number, then prints to stdout **only when `outFile is None`**.

## Key facts / gotchas
- `outFile` is always passed as `None` across the codebase; the file-output branch is effectively unimplemented — if `outFile` is set, `.print()` does nothing (no write, no console). So a non-None `outFile` silently swallows logs.
- Pure side-effect (stdout); returns nothing and never errors. Safe to call anywhere.

## Touchpoints
- Called by: nearly all modules (LexicalAnalizer, Message, MessageCreator, pre_lex, ...).
- Depends on: stdlib `inspect` only.
