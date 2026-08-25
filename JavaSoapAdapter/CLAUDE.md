# JavaSoapAdapter — Java target: hand-rolled SOAP envelope access over JDK-builtin HttpServer

**Pipeline role:** Java-target Stage 11 equivalent (sessions J.15 envelope parsing, J.16 acceptance gate — landed together, `initiatives/multi-language-targets/thread-1-java-target`). A direct port of `Database/SoapAdapter.py`'s hand-rolled envelope get/set/update/delete parsing — **not a real SOAP/WS-* stack** even on the C++ side (`Database/CLAUDE.md`), and Java's own removal of JAX-WS from the JDK (since 11) is irrelevant here for exactly that reason: this was never going to use a real SOAP toolkit regardless of language.
**Entry point (from main.py):** gated behind `HARPIA_GEN_LANG=java`, called right after `JavaRestAdapter` in the same block: `JavaSoapAdapter(messages=msgFactory.messages, dest=testDestination, compliance=complianceContext).Process()`. Returns `None` or an `Error` (non-fatal; main.py logs it).
**Inputs → Outputs:** consumes message objects (same table-bearing filter as REST/`Database/SoapAdapter.py`). Emits `<dest>/java/src/main/java/com/harpia/runtime/soap/SoapHelpers.java` (shared) and `<dest>/java/src/main/java/com/harpia/generated/soap/<name>_soap.java` (one per table-bearing message).

## Files
- `runtime/SoapHelpers.java` — hand-written (NOT generated), copied verbatim. A direct port of the C++ template's `detail::` namespace (`local_name`/`find_child`/`child_text`) onto `org.w3c.dom` — the same DOM type `JavaXmlAdapter`'s `HarpiaXml` already uses, so no new XML library, no new dependency. Adds `childInt()` (graceful `0` on a missing/unparseable `<id>`, matching the C++ target's `idEl && idEl->GetText() ? atoll(...) : 0` rather than throwing) and `authorized(doc, user, pswd)` (parameterized, same reasoning as `JavaRestAdapter`'s own `authorized()` — no per-message closure needed).
- `templates/soap.java.tmpl` — per-message `com.harpia.generated.soap.<name>_soap`: `register(HttpServer, Connection, String base)` wires one `HttpServer.createContext` at `<base>/<name>` (POST only — SOAP has no separate item path, the id lives in the envelope body); `handle()` parses the envelope, gates on the SOAP-Header credential, dispatches on the Body's first child element's local name (`get`/`set`/`update`/`delete`); each operation calls the DAO and wraps its own XML fragment in `SoapHelpers.envelope(...)`, reusing `HarpiaXml.toXml`/`fromXmlElement` (already generic) for the message payload itself.

## Response status codes (ported faithfully from the C++ template, not re-decided)
- **401** for an authentication failure (with a `<soap:Fault>` body).
- **400** for a malformed envelope, or a `set`/`update` op with no message element.
- **200** for everything else, INCLUDING a "not found" (`get`/no matching row) or "unknown operation" fault — these come back as a `<soap:Fault>` body at HTTP 200, exactly matching the C++ target's own `soap.h.tmpl` (which never sets `res.code` before that particular `reply()`, so Crow's default 200 stands). Not upgraded to a more RESTful-feeling status here — parity with the existing, already-shipped C++ behavior wins over a "more correct" status this session didn't ask for.

## Key facts / gotchas
- **No item path** — unlike `JavaRestAdapter`'s `trailingId()`, SOAP's single POST endpoint carries the operation AND the id/message entirely in the Body, so there's nothing to recover from the URL path at all.
- **Shares `JavaRestAdapter`'s `HttpRestHelpers`** for `readBody`/`sendBody`/`sendStatus` — those are pure HTTP-exchange mechanics with no REST-specific meaning, so SOAP reuses them directly rather than duplicating (or, worse, forking) that logic into a second copy.
- `HarpiaXml.fromXmlElement(Element, Builder)` (added in J.10/J.11 specifically for this kind of batch/embedded use — see `XmlAdapter/CLAUDE.md`'s C++ analogue `from_xml_element`) is what lets `set`/`update` hand the `<{name}>...</{name}>` element straight to the XML runtime without re-serializing it to a string and re-parsing.
- WSDL generation is deferred here exactly as it is on the C++ side (`Database/SoapAdapter.py`'s own docstring: "WSDL generation is deferred") — not a Java-specific gap.

## Touchpoints
- Called by: `main.py`, gated on `HARPIA_GEN_LANG=java`, right after `JavaRestAdapter` in the same conditional block.
- Depends on: `JavaDatabase` (`<name>_dao`), `JavaXmlAdapter` (`HarpiaXml`), `JavaRestAdapter` (`HttpRestHelpers`), `Util.util.copy_if_different`/`write_if_different`/`loadTemplate`, `Logger.logger`, `Errors.Error`.
