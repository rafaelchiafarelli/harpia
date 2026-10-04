"""A small HTTP router over :mod:`http.server` (the Python side of the C++
target's Crow app; stdlib only).

Hand-written, copied into a generated project as
``harpia_runtime.http.router``. Generated REST/SOAP modules register routes
on one :class:`Router`; :func:`make_server` serves it on a
:class:`~http.server.ThreadingHTTPServer` (one thread per request).

- Paths match segment by segment; ``<id>`` matches a signed integer and is
  passed to the handler as ``req.params["id"]``.
- No route → 404; a known path with another method → 405.
- Bodies over :data:`MAX_BODY` → 413 before the handler runs.
- A handler that raises gets a 500; the exception never reaches the
  server loop.
- Content negotiation helpers: :func:`body_is_xml` (``Content-Type``
  contains ``xml``) and :func:`wants_xml` (``Accept`` contains ``xml``),
  as in C++.
"""
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

#: largest accepted request body (bytes)
MAX_BODY = 1 << 20

_INT = re.compile(r"-?\d+")


@dataclass
class Request:
    """One parsed request."""

    method: str
    path: str
    #: first value of each query parameter
    query: dict[str, str]
    #: header names lower-cased
    headers: dict[str, str]
    body: bytes = b""
    #: path parameters (``id``)
    params: dict[str, int] = field(default_factory=dict)
    #: free slot for the transport (e.g. the TLS peer certificate's CN)
    peer: dict[str, Any] = field(default_factory=dict)

    def header(self, name: str) -> str:
        """A header value (case-insensitive), ``""`` when absent."""
        return self.headers.get(name.lower(), "")


@dataclass
class Response:
    """What a handler returns."""

    status: int
    body: bytes = b""
    content_type: str = "text/plain"
    headers: dict[str, str] = field(default_factory=dict)


Handler = Callable[[Request], Response]


def text(status: int, message: str = "") -> Response:
    """A ``text/plain`` response."""
    return Response(status, message.encode(), "text/plain")


def body_is_xml(req: Request) -> bool:
    """The request body is XML (``Content-Type`` mentions ``xml``)."""
    return "xml" in req.header("Content-Type")


def wants_xml(req: Request) -> bool:
    """The client asks for XML (``Accept`` mentions ``xml``)."""
    return "xml" in req.header("Accept")


class Router:
    """Method + path dispatch."""

    def __init__(self) -> None:
        self._routes: list[tuple[str, list[str], Handler]] = []

    def add(self, method: str, path: str, handler: Handler) -> None:
        """Route ``method path`` (``<id>`` segments match integers)."""
        self._routes.append((method.upper(), path.strip("/").split("/"), handler))

    @staticmethod
    def _match(pattern: list[str], parts: list[str]) -> dict[str, int] | None:
        if len(pattern) != len(parts):
            return None
        params: dict[str, int] = {}
        for want, got in zip(pattern, parts, strict=True):
            if want == "<id>":
                if not _INT.fullmatch(got):
                    return None
                params["id"] = int(got)
            elif want != got:
                return None
        return params

    def dispatch(self, req: Request) -> Response:
        """Run the matching handler; 404 / 405 / 500 otherwise."""
        parts = req.path.strip("/").split("/")
        allowed = False
        for method, pattern, handler in self._routes:
            params = self._match(pattern, parts)
            if params is None:
                continue
            allowed = True
            if method != req.method:
                continue
            req.params = params
            try:
                return handler(req)
            except Exception:
                return text(500, "internal error")
        return text(405 if allowed else 404)


def _handler_class(router: Router) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _serve(self) -> None:
            url = urlsplit(self.path)
            headers = {k.lower(): v for k, v in self.headers.items()}
            length = int(headers.get("content-length", "0") or 0)
            if length > MAX_BODY:
                self._reply(text(413, "request body too large"))
                self.close_connection = True
                return
            body = self.rfile.read(length) if length > 0 else b""
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            req = Request(self.command, url.path, query, headers, body)
            req.peer.update(self._peer())
            self._reply(router.dispatch(req))

        def _peer(self) -> dict[str, Any]:
            return {"address": self.client_address}

        def _reply(self, res: Response) -> None:
            self.send_response(res.status)
            self.send_header("Content-Type", res.content_type)
            self.send_header("Content-Length", str(len(res.body)))
            for name, value in res.headers.items():
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(res.body)

        do_GET = do_POST = do_PUT = do_DELETE = _serve

        def log_message(self, format: str, *args: Any) -> None:
            return None  # quiet; generated servers log through their own code

    return _Handler


class Server:
    """A :class:`Router` served on a background thread."""

    def __init__(self, router: Router, host: str = "127.0.0.1", port: int = 0) -> None:
        self._httpd = ThreadingHTTPServer((host, port), _handler_class(router))
        self._httpd.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The bound port (useful with ``port=0``)."""
        return int(self._httpd.server_address[1])

    @property
    def httpd(self) -> ThreadingHTTPServer:
        """The underlying server (TLS wrapping hooks in here)."""
        return self._httpd

    def start(self) -> None:
        """Serve in a daemon thread."""
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True,
                                        name="harpia-http")
        self._thread.start()

    def stop(self) -> None:
        """Stop serving and close the socket."""
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join()


def make_server(router: Router, host: str = "127.0.0.1", port: int = 0) -> Server:
    """A :class:`Server` for ``router`` (not started)."""
    return Server(router, host, port)
