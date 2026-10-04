# PyHttp — the Python target's HTTP transports (REST; SOAP from task 3)

**Pipeline role / purpose:** python-target / py-transports-http. The Python
side of `Database/RestAdapter.py` (+ `SoapAdapter`, the shared HTTP
bring-up). A stage of `LangBackend/python.py`'s `run_python`, after
`PyZmqAdapter`.

**Entry point:** `PyHttpAdapter(messages, dest, compliance).Process()` →
`None` (nothing when no table-bearing message exists).

## Runtimes (copied as `harpia_runtime.http.*`)
- `runtime/router.py` → `.router`: `Request` (lower-cased headers,
  first-value query, `params["id"]`, `peer` slot), `Response`, `text()`,
  `Router` (`add(method, path)` with `<id>` integer segments; 404 / 405;
  a raising handler → 500), `body_is_xml` / `wants_xml` (C++ content
  negotiation), `MAX_BODY` (1 MiB → 413 before reading), `Server` /
  `make_server` (`ThreadingHTTPServer`, daemon threads, `port`, `start`,
  `stop`, `httpd` for TLS wrapping later).
- `runtime/rest.py` → `.rest`: `register_crud(router, pool, base, name,
  dao_class, message_type, gate, default_limit)` — the five C++ routes and
  answers (201 / 200 / 204 / 404 / 400 / 500; list `[...]` or
  `<list>...</list>`; `?limit=&offset=`), gate first, then one pooled
  connection per request (503 `db pool exhausted` / `db reconnect failed`).
  `Gate = Callable[[Request, op], Response | None]`; `flat_gate(user, pswd)`.

## Generated (under `harpia_generated/`)
- `rest/<name>_<hash>_rest.py` per table-bearing message (= the C++
  `rest/*_rest.h` set): `DEFAULT_LIMIT` (`pagination_default`), `GATE`,
  `register(router, pool, base="")`.
- `http/http_server_bringup.py`: `HttpServer(pool, host="127.0.0.1",
  port=0, rest_base="", soap_base="/soap")` registering every REST module
  on one `Router` (`REST_MESSAGES`), `port` / `start` / `stop`.

## Key facts / gotchas
- **As C++:** PUT / DELETE answer 204 even when no row matched (the C++
  DAO's update/remove return true either way); PUT ignores the path id
  (the body's key is used); reconnect failure is 503 like exhaustion.
- Task 2 emits the flat gate for every message; the hardened gates
  (mTLS identity, RBAC, sessions) replace it per message in tasks 5–7.
- A client that keeps uploading a body > 1 MiB sees a broken pipe: the
  413 is sent before the body is read (by design: no draining).
- One C++ HTTP client (`UnitTests/harpia_test_client.h`) drives this
  server through the same paths it uses against Crow.

## Touchpoints
- Depends on: `Database.model.pagination_default`, the generated DAOs,
  `harpia_runtime.db.pool`, the JSON/XML runtimes.
- Tested by: `UnitTests/test_py_rest.py`.
