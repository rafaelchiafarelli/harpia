## REST CRUD over `http.server` + a hand-rolled router + shared HTTP bring-up

- **Depends on:** task 1; `py-serialization` tasks 1–2.
- **Contract:**
  - `harpia_runtime/http/router.py`: method + path matching with an
    `<id>` segment, content negotiation (XML if Content-Type/Accept says
    `xml`, else JSON), body read/size limit, status helpers.
  - Generated `harpia_generated/rest/<name>_<hash>_rest.py` per
    table-bearing message, `register(router, pool, base)`:
    - `GET <base>/<name>` lists, paginated by `?limit=&offset=`; the
      message's `pagination_default()` is the default limit, as in C++;
    - `GET` / `PUT` / `DELETE <base>/<name>/<id>`;
    - `POST <base>/<name>`.

    Each request borrows one pooled connection: `PoolExhausted` → 503,
    any other error → 500. The handler never leaks an exception.
  - **Flat credential gate** (non-hardened projects): `X-User == "<name>"`
    and `X-Pswd == "<hash>"`, else 401. This is the C++ flat variant.
    Hardened gates come in tasks 5–7.
  - Generated `harpia_generated/http/http_server_bringup.py`: an
    `HttpServer(pool, host, port, rest_base, soap_base)` class that
    registers every REST route (and SOAP's, after task 3) on one
    `ThreadingHTTPServer`, with `start()`/`stop()`. This is the counterpart
    of C++ `http_server_bringup.h`.
- **Bar:** the request/response contract (paths, status codes, JSON/XML
  bodies, pagination) matches the C++ REST surface, so one HTTP client
  works against either. The C++ client-side test helper can drive the
  Python server.
- **Out of scope:** TLS (5), RBAC (6), sessions (7), capability route
  (`py-versioning`).
- **Tests:** a generated-project server test per verb, under the flat
  profile, with both content types. 401 without/with wrong credentials.
  Pagination. 503 when the pool is exhausted (pool size 1, one borrow held).
