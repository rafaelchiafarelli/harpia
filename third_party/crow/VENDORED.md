# Crow (vendored)

- **Version:** 1.3.2
- **Source:** https://github.com/CrowCpp/Crow (release `v1.3.2`, asset `crow_all.h`)
- **License:** BSD-3-Clause (see LICENSE; the amalgamated header also bundles
  ISC/MIT-licensed portions, noted in its SPDX header)
- **Files:** `crow.h` (the upstream amalgamated single header `crow_all.h`, renamed)

Vendored in-tree (rather than installed from a package manager) so the exact
third-party source used by harpia's Stage 11 (SOAP) and Stage 12 (REST) layers is
tracked with the project. Header-only, like the cpp-httplib it replaces.

Crow requires **asio**; we use standalone asio (no Boost) vendored in `../asio/`.
Crow defines `ASIO_STANDALONE` itself, so nothing extra is needed at the build
site beyond putting both `third_party/crow` and `third_party/asio` on the include
path and linking `pthread`. `CROW_USE_BOOST` is left unset. `CROW_ENABLE_SSL` is
opt-in per build (the transport-authn epic's REST/SOAP mTLS uses it; it links
OpenSSL — `-lssl -lcrypto`).

**Latest upstream is v1.3.3, but that release dropped the `crow_all.h` asset**, so
v1.3.2 is the newest amalgamated header available.

## Local patches (must be re-applied on any re-vendor)

`crow.h` carries harpia edits, each tagged with a `[harpia patch]` comment.
`grep -n "\[harpia patch\]" crow.h` lists them. To re-vendor: drop in the new
`crow_all.h`, then re-apply each hunk below.

1. **Client-certificate CN exposed to route handlers** (transport-authn epic,
   task 4 — RBAC). Upstream Crow never surfaces the peer's X.509 cert to a
   handler (`request` carries only `remote_ip_address`). Added:
   - `struct request`: new field `std::string client_cert_cn;`
   - `SSLAdaptor`: `std::string peer_cert_cn() const` — `SSL_get_peer_certificate`
     → `X509_NAME_get_text_by_NID(..., NID_commonName, ...)` → `X509_free`.
   - `TCPAdaptor` / `UnixSocketAdaptor`: `std::string peer_cert_cn() const { return {}; }`
     (no client cert on a non-TLS connection).
   - `Connection::handle()`: `req_.client_cert_cn = adaptor_.peer_cert_cn();`
     right after the existing `req_.remote_ip_address = adaptor_.address();`.

   The generated RBAC gate (`Database/templates/{rest,soap}.h.tmpl`) reads
   `req.client_cert_cn`; on a hardened (mTLS) build the value is a
   handshake-verified identity, on a plain-HTTP build it is `""`.

To update: replace `crow.h` from a newer release's `crow_all.h`, bump the version
above, re-apply the patches above, and re-check the compatible asio version in
`../asio/VENDORED.md`.
