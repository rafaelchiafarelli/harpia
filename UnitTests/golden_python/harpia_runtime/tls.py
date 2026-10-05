"""Fail-safe mTLS for the generated servers and their clients (the Python
side of ``harpia_http_mtls.h`` / ``harpia_grpc_mtls.h``).

Hand-written, copied into a generated project as ``harpia_runtime.tls``.

- :class:`MtlsFiles` names the three PEM files a peer needs (CA, its own
  certificate chain, its private key). A generated project ships none; a
  deployment provisions them (``Assets/cmake/mtls_provision.sh`` makes a
  dev PKI that C++ and Python peers share).
- Server side: :func:`http_server_context` / :func:`grpc_server_credentials`
  return ``None`` (plaintext) when hardening is not required; otherwise a
  verified-client-certificate configuration. ``client_cert_required=False``
  is mixed mode: a certless client may connect, a presented certificate is
  still verified (HTTP: ``CERT_OPTIONAL``).
- **Fail-safe:** hardening required and :meth:`MtlsFiles.complete` false →
  :class:`SecurityRefused`. Never a silent plaintext server.
- Client side: :func:`http_client_context` / :func:`grpc_channel_credentials`.
- The verified client certificate's subject CN: :func:`cn_from_peercert`
  (HTTP, from ``SSLSocket.getpeercert()``) and :func:`grpc_peer_cn`.

**gRPC mixed mode (Python limitation):** ``grpc.ssl_server_credentials``
only offers "require and verify" or "don't request", so with
``client_cert_required=False`` a gRPC server never sees a client
certificate -- every gRPC caller is anonymous there and ``protected``
messages are refused over gRPC (fail-closed). HTTP mixed mode verifies a
presented certificate as C++ does.
"""
import os
import ssl
from dataclasses import dataclass
from typing import Any

import grpc


class SecurityRefused(RuntimeError):
    """Hardening is required but the TLS material is missing or unreadable."""


@dataclass(frozen=True)
class MtlsFiles:
    """Paths of one peer's PEM files."""

    ca_certificate: str = ""
    certificate: str = ""
    private_key: str = ""

    def complete(self) -> bool:
        """All three paths are set."""
        return bool(self.ca_certificate and self.certificate and self.private_key)


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise SecurityRefused(f"cannot read PEM file: {path}") from e


def _need(files: MtlsFiles | None, side: str) -> MtlsFiles:
    if files is None or not files.complete():
        raise SecurityRefused(
            f"mTLS refused: incomplete MtlsFiles (need CA certificate + {side} "
            "certificate + private key)")
    for path in (files.ca_certificate, files.certificate, files.private_key):
        if not os.path.exists(path):
            raise SecurityRefused(f"mTLS refused: cannot read PEM file: {path}")
    return files


def http_server_context(hardening_required: bool, files: MtlsFiles | None,
                        client_cert_required: bool = True) -> ssl.SSLContext | None:
    """The server's TLS context, or ``None`` for plaintext."""
    if not hardening_required:
        return None
    f = _need(files, "server")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        ctx.load_cert_chain(f.certificate, f.private_key)
        ctx.load_verify_locations(f.ca_certificate)
    except (ssl.SSLError, OSError) as e:
        raise SecurityRefused(f"mTLS refused: bad PEM material: {e}") from e
    ctx.verify_mode = ssl.CERT_REQUIRED if client_cert_required else ssl.CERT_OPTIONAL
    return ctx


def http_client_context(files: MtlsFiles | None) -> ssl.SSLContext:
    """A client context presenting ``files.certificate`` and trusting
    ``files.ca_certificate`` (hostname checking stays on)."""
    f = _need(files, "client")
    ctx = ssl.create_default_context(cafile=f.ca_certificate)
    ctx.load_cert_chain(f.certificate, f.private_key)
    return ctx


def grpc_server_credentials(hardening_required: bool, files: MtlsFiles | None,
                            client_cert_required: bool = True
                            ) -> grpc.ServerCredentials | None:
    """The server's gRPC credentials, or ``None`` for an insecure port."""
    if not hardening_required:
        return None
    f = _need(files, "server")
    return grpc.ssl_server_credentials(
        [(_read(f.private_key), _read(f.certificate))],
        root_certificates=_read(f.ca_certificate),
        require_client_auth=client_cert_required)


def grpc_channel_credentials(files: MtlsFiles | None) -> grpc.ChannelCredentials:
    """Client-side gRPC credentials presenting ``files.certificate``."""
    f = _need(files, "client")
    return grpc.ssl_channel_credentials(
        root_certificates=_read(f.ca_certificate),
        private_key=_read(f.private_key), certificate_chain=_read(f.certificate))


def cn_from_peercert(cert: Any) -> str:
    """The subject commonName of an ``SSLSocket.getpeercert()`` dict, or ``""``."""
    if not cert:
        return ""
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName":
                return str(value)
    return ""


def grpc_peer_cn(context: grpc.ServicerContext) -> str:
    """The verified client certificate's CN for a gRPC call, or ``""``."""
    values = context.auth_context().get("x509_common_name") or []
    return str(values[0].decode("utf-8", "replace")) if values else ""
