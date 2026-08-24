### Session J.14 — REST acceptance gate

- **Depends on:** J.13 merged.
- **Deliverable:** nothing new — closes the loop for REST.
- **Acceptance gate:** live REST CRUDL cycle matches the C++ target's
  behavior for the same schema.

## Implementation notes (landed 2026-08-23, together with J.12/J.13)

`tests/test_java_rest.py::test_rest_crud_cycle_over_http` — a real
`HttpServer` on an ephemeral port, driven with `java.net.http.HttpClient`
(not the generated Java code calling itself in-process): rejects a
credential-less request (401), then a full create (JSON body) / read
(requested back as XML, proving content negotiation dispatches for real,
not just that both runtimes exist) / update / list / delete cycle against
`users`, ending with a 404 confirming the delete took. Not run in this
environment (no gradle/JDK here), same status as every other Java
integration test this thread has added.

**Same deferred-scope note as `DB-CRUDL-SQLITE`/`DB-CRUDL-POSTGRES`'s own
acceptance gates:** this proves the REST surface for what J.6/J.13 actually
built (unpaginated CRUD over top-level scalar/enum columns), not full C++
RestAdapter parity.
