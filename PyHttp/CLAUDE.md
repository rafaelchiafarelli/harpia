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

- `runtime/soap.py` → `harpia_runtime.soap` (task 3, port of
  `harpia_soap.h`): `local_name` / `find_child` / `child_text` /
  `parse_envelope` / `find_operation` / `message_from_request` +
  `envelope()` / `fault()`. **No namespace processing** (expat without a
  namespace separator, building an `ElementTree`): names stay
  `prefix:local` and an undeclared prefix parses, exactly as tinyxml2.
  **Decision (task 3):** no `defusedxml`; any `<!DOCTYPE` / `<!ENTITY>` is
  refused before parsing (SOAP forbids DTDs) and expat's doctype/entity
  handlers refuse as a second line — so no entity expansion; size is
  bounded by the router's `MAX_BODY`. Never raises.
- `runtime/soap_endpoint.py` → `.http.soap_endpoint`: `register_soap(router,
  pool, base, name, dao_class, message_type, early_gate=None,
  op_gate=None)` — the C++ order (parse → early gate → operation → op gate
  → pool → dispatch) and answers (400 / 401 `Client.Authentication` Fault /
  503 Fault / 200 for everything else incl. "not found" and "unknown
  operation"); `flat_soap_gate(user, pswd)`; `xml_reply`.

- `runtime/tls.py` → `harpia_runtime.tls` (task 5; also copied by
  `PyGrpcAdapter`): `MtlsFiles(ca_certificate, certificate, private_key)`
  + `complete()`, `SecurityRefused`, `http_server_context` /
  `grpc_server_credentials` (`None` = plaintext when hardening isn't
  required; `client_cert_required=False` = mixed mode), client-side
  `http_client_context` / `grpc_channel_credentials`, `cn_from_peercert`,
  `grpc_peer_cn`. Incomplete or unreadable files → `SecurityRefused`,
  never plaintext. `router.Server(tls=...)` wraps each connection on its
  worker thread (a failed handshake drops just that connection) and puts
  `getpeercert()` in `req.peer["cert"]`.
  **Python limitation (logged):** `grpc.ssl_server_credentials` has only
  require-and-verify or don't-request, so gRPC mixed mode never sees a
  client certificate — every gRPC caller is anonymous there (fail-closed
  for `protected`); HTTP mixed mode (`CERT_OPTIONAL`) verifies a presented
  cert like C++.

- `runtime/rbac_gates.py` → `harpia_runtime.rbac_gates` (task 6; copied
  with `harpia_runtime.rbac` + its audit sink by `copy_rbac_runtimes`, from
  PyHttp **and** PyGrpc, only when some message is RBAC-gated — the C++
  "copy `harpia_rbac.h` only if any_rbac" rule): `rest_rbac_gate(subject)`
  (401 / 403, empty body), `soap_rbac_gate(subject)` (an *op gate*: `get`
  read / `set` create / `update` / `delete` remove, unknown ops ungated;
  401 / 403 `Client.Authentication` Fault `unauthenticated` / `forbidden`),
  `grpc_rbac_gate(subject)` (`UNAUTHENTICATED "unauthenticated"` /
  `PERMISSION_DENIED "forbidden"`), `http_peer_cn`. Identity = the verified
  client-cert CN. The RBAC mechanism itself (`Role`, `Operation`,
  `permitted`, `RoleMap`, `role_map()`, `decide`) is
  `Compliance/runtime/python/rbac.py`.

## Generated (under `harpia_generated/`)
- `rest/<name>_<hash>_rest.py` per table-bearing message (= the C++
  `rest/*_rest.h` set): `DEFAULT_LIMIT` (`pagination_default`), `GATE`,
  `register(router, pool, base="")`. `GATE` is `rest_rbac_gate(name)` when
  `Database.auth_gate.effective_rbac(msg, hardening)` (the C++ choice,
  imported, not re-implemented), else `flat_gate(name, hash)`.
- `soap/<name>_<hash>_soap.py` per table-bearing message: `WSDL` (the
  existing `wsdl/<name>_<hash>.wsdl`, not regenerated), `EARLY_GATE` (flat)
  or `OP_GATE` (RBAC, after the operation parse — the C++ order),
  `register(router, pool, base="/soap")`.
- `http/http_server_bringup.py`: `HttpServer(pool, host="127.0.0.1",
  port=0, rest_base="", soap_base="/soap")` registering every REST and SOAP
  module on one `Router` (`REST_MESSAGES`), `port` / `start` / `stop`,
  `mtls=MtlsFiles`. Bakes `HARDENING_REQUIRED`, and `EMIT_TLS` /
  `CLIENT_CERT_REQUIRED` only when `auth_gate.transport_mode` diverges (the
  C++ rule; the HarpiaTest fixture diverges, so even its low-risk build
  needs PKI — flat-gate tests register bindings on a plain `Server`).

## Key facts / gotchas
- **SOAP parity is byte-for-byte:** one ordered request sequence against
  the C++ (Crow) endpoint and the Python one gives identical statuses and
  envelopes (`test_same_envelopes_as_cpp`); only Crow's default body for a
  bodyless error (`400 Bad Request\r\n`) differs — Python sends empty.
- SOAP `update`/`delete` answer `<ok>true</ok>` unless the DB errors (as
  C++); a `get` whose read raises is "not found".
- **As C++:** PUT / DELETE answer 204 even when no row matched (the C++
  DAO's update/remove return true either way); PUT ignores the path id
  (the body's key is used); reconnect failure is 503 like exhaustion.
- Gates per message since task 6 (flat vs RBAC, the C++ `effective_rbac`
  choice); bearer sessions on top of RBAC are task 7. **Parity (task 6):**
  for one RBAC map file + one PKI, the generated C++ and Python
  `HttpServer`s answer the same 5-identity × 12-request sequence with the
  same statuses and byte-identical SOAP envelopes (`test_py_rbac.py`).
- A client that keeps uploading a body > 1 MiB sees a broken pipe: the
  413 is sent before the body is read (by design: no draining).
- One C++ HTTP client (`UnitTests/harpia_test_client.h`) drives this
  server through the same paths it uses against Crow.

## Touchpoints
- Depends on: `Database.model.pagination_default`, the generated DAOs,
  `harpia_runtime.db.pool`, the JSON/XML runtimes.
- Tested by: `UnitTests/test_py_rest.py`, `test_py_soap.py`,
  `test_py_mtls.py`, `test_py_rbac.py`.
