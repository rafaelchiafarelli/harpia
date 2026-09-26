## `HttpServer` (REST + SOAP) over a `soci::connection_pool`

- **Depends on:** task 1 (same pattern, same review).
- **Contract:** `http/http_server_bringup.h`'s `HttpServer::Configure` gains a
  `::soci::connection_pool&` overload, and generated REST/SOAP route handlers
  borrow one session per request. Additive, like task 1.
- **Pre-work:** none.
- **Out of scope:** anything gRPC; the reference system doesn't use REST/SOAP,
  but leaving Crow's multithreaded handlers on one shared session would keep
  the same race in the other half of the generated server.
- **Tests:** the task 1 concurrency test pattern against REST and SOAP
  endpoints; goldens regenerated and reviewed.
